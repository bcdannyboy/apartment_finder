from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, Optional

from services.acquisition.audit import AuditLogger
from services.acquisition.errors import AdapterValidationError, TransientNetworkError, UpstreamRateLimitError
from services.acquisition.models import FirecrawlRequest, TaskSpec, TaskStatus
from services.acquisition.queue import QueueBackend
from services.acquisition.rate_limiter import Clock, DomainRateLimiter
from services.acquisition.repository import TaskRepository
from services.acquisition.validation import FIRECRAWL_TASKS
from services.policy_gate.models import PolicyEvaluateRequest
from services.policy_gate.service import PolicyGateService


class TaskWorker:
    def __init__(
        self,
        *,
        repository: TaskRepository,
        queue: QueueBackend,
        policy_gate: PolicyGateService,
        audit_logger: AuditLogger,
        rate_limiter: DomainRateLimiter,
        firecrawl_handler: Callable[[TaskSpec], object],
        clock: Optional[Clock] = None,
    ) -> None:
        self._repository = repository
        self._queue = queue
        self._policy_gate = policy_gate
        self._audit_logger = audit_logger
        self._rate_limiter = rate_limiter
        self._firecrawl_handler = firecrawl_handler
        self._clock = clock or Clock()

    def _policy_decision(self, task: TaskSpec) -> tuple[bool, Optional[str], str]:
        request = PolicyEvaluateRequest(
            schema_version="v1",
            source_id=task.source_id,
            domain=task.domain,
            task_type=task.task_type,
            requested_operation="automated_fetch",
        )
        decision = self._policy_gate.evaluate(request)
        allowed = task.task_type in decision.allowed_operations
        return allowed, decision.policy_id, decision.reason

    def _enqueue_with_delay(self, task: TaskSpec, scheduled_at: datetime) -> None:
        task.scheduled_at = scheduled_at
        self._repository.update_status(task.task_id, TaskStatus.queued, self._clock.now())
        self._queue.enqueue(task, scheduled_at)

    def _log_outcome(
        self,
        task: TaskSpec,
        *,
        outcome: str,
        policy_id: Optional[str],
        error_class: Optional[str] = None,
        params: Optional[Dict[str, object]] = None,
    ) -> None:
        self._audit_logger.log(
            task_id=task.task_id,
            policy_id=policy_id,
            outcome=outcome,
            params=params or {"task_type": task.task_type.value},
            attempt=task.attempt,
            error_class=error_class,
            source_id=task.source_id,
            domain=task.domain,
        )

    def _execute_task(self, task: TaskSpec) -> None:
        if task.task_type in FIRECRAWL_TASKS:
            self._firecrawl_handler(task)
        else:
            return

    def process_task(self, task_id: str) -> None:
        task = self._repository.get(task_id)
        if task is None:
            return

        allowed, policy_id, reason = self._policy_decision(task)
        task.policy_id = policy_id or task.policy_id
        if not allowed:
            self._repository.update_status(task.task_id, TaskStatus.denied, self._clock.now())
            self._log_outcome(task, outcome="denied", policy_id=policy_id, error_class="PolicyDenied")
            return

        delay_until = self._rate_limiter.acquire(task.domain)
        if delay_until is not None:
            self._enqueue_with_delay(task, delay_until)
            return

        self._repository.update_status(task.task_id, TaskStatus.running, self._clock.now())
        attempt = self._repository.increment_attempt(task.task_id)

        try:
            self._execute_task(task)
        except AdapterValidationError as exc:
            self._repository.update_status(task.task_id, TaskStatus.failed, self._clock.now())
            self._rate_limiter.release(task.domain, success=False)
            self._log_outcome(
                task,
                outcome="failed",
                policy_id=policy_id,
                error_class=exc.__class__.__name__,
                params={"reason": str(exc), "task_type": task.task_type.value},
            )
            return
        except UpstreamRateLimitError as exc:
            cooldown = self._rate_limiter.register_error(task.domain)
            self._rate_limiter.release(task.domain, success=False)
            if attempt < task.max_attempts:
                self._enqueue_with_delay(task, cooldown)
                self._log_outcome(
                    task,
                    outcome="failed",
                    policy_id=policy_id,
                    error_class=exc.__class__.__name__,
                    params={"reason": str(exc), "task_type": task.task_type.value},
                )
                return
            self._repository.update_status(task.task_id, TaskStatus.failed, self._clock.now())
            self._log_outcome(
                task,
                outcome="failed",
                policy_id=policy_id,
                error_class=exc.__class__.__name__,
                params={"reason": str(exc), "task_type": task.task_type.value},
            )
            return
        except TransientNetworkError as exc:
            cooldown = self._rate_limiter.register_error(task.domain)
            self._rate_limiter.release(task.domain, success=False)
            if attempt < task.max_attempts:
                self._enqueue_with_delay(task, cooldown)
                self._log_outcome(
                    task,
                    outcome="failed",
                    policy_id=policy_id,
                    error_class=exc.__class__.__name__,
                    params={"reason": str(exc), "task_type": task.task_type.value},
                )
                return
            self._repository.update_status(task.task_id, TaskStatus.failed, self._clock.now())
            self._log_outcome(
                task,
                outcome="failed",
                policy_id=policy_id,
                error_class=exc.__class__.__name__,
                params={"reason": str(exc), "task_type": task.task_type.value},
            )
            return
        except Exception as exc:  # pragma: no cover - safety net
            self._rate_limiter.release(task.domain, success=False)
            self._repository.update_status(task.task_id, TaskStatus.failed, self._clock.now())
            self._log_outcome(
                task,
                outcome="failed",
                policy_id=policy_id,
                error_class=exc.__class__.__name__,
                params={"reason": str(exc), "task_type": task.task_type.value},
            )
            return

        self._rate_limiter.release(task.domain, success=True)
        self._repository.update_status(task.task_id, TaskStatus.succeeded, self._clock.now())
        self._log_outcome(task, outcome="succeeded", policy_id=policy_id)


def firecrawl_task_handler(adapter, *, source_id: str, task: TaskSpec):
    payload = task.payload or {}
    request = FirecrawlRequest(
        schema_version="v1",
        url=payload.get("url"),
        formats=payload.get("formats", {}),
        change_tracking=payload.get("change_tracking"),
        metadata=payload.get("metadata"),
    )
    return adapter.fetch_and_store(task_id=task.task_id, source_id=source_id, request=request)
