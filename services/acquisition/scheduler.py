from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

from services.acquisition.audit import AuditLogger
from services.acquisition.errors import QueuePayloadError, TaskValidationError
from services.acquisition.models import TaskSpec, TaskStatus
from services.acquisition.queue import QueueBackend
from services.acquisition.rate_limiter import Clock, DomainRateLimiter
from services.acquisition.repository import TaskRepository
from services.acquisition.validation import validate_queue_payload, validate_task_schema
from services.policy_gate.models import PolicyEvaluateRequest
from services.policy_gate.service import PolicyGateService


class TaskScheduler:
    def __init__(
        self,
        *,
        queue: QueueBackend,
        repository: TaskRepository,
        policy_gate: PolicyGateService,
        audit_logger: AuditLogger,
        rate_limiter: DomainRateLimiter,
        clock: Optional[Clock] = None,
    ) -> None:
        self._queue = queue
        self._repository = repository
        self._policy_gate = policy_gate
        self._audit_logger = audit_logger
        self._rate_limiter = rate_limiter
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

    def _deny_task(self, task: TaskSpec, reason: str, policy_id: Optional[str], error_class: str) -> None:
        task.status = TaskStatus.denied
        self._repository.add(task)
        self._audit_logger.log(
            task_id=task.task_id,
            policy_id=policy_id,
            outcome="denied",
            params={"reason": reason, "task_type": task.task_type.value},
            attempt=task.attempt,
            error_class=error_class,
            source_id=task.source_id,
            domain=task.domain,
        )

    def submit_raw(self, payload: dict) -> Optional[TaskSpec]:
        try:
            task = validate_task_schema(payload)
        except TaskValidationError as exc:
            task_id = payload.get("task_id", "unknown")
            self._audit_logger.log(
                task_id=task_id,
                policy_id=payload.get("policy_id"),
                outcome="denied",
                params={"reason": "schema_validation", "detail": str(exc)},
                attempt=0,
                error_class="TaskValidationError",
                source_id=payload.get("source_id"),
                domain=payload.get("domain"),
            )
            return None
        return self.submit_task(task)

    def submit_task(self, task: TaskSpec) -> Optional[TaskSpec]:
        try:
            validate_queue_payload(task)
        except QueuePayloadError as exc:
            self._deny_task(task, str(exc), task.policy_id, "QueuePayloadError")
            return None

        allowed, policy_id, reason = self._policy_decision(task)
        task.policy_id = policy_id or task.policy_id
        if not allowed:
            self._deny_task(task, reason, policy_id, "PolicyDenied")
            return None

        scheduled_at = max(task.scheduled_at, self._rate_limiter.next_available_time(task.domain))
        task.scheduled_at = scheduled_at
        task.status = TaskStatus.queued
        self._repository.add(task)
        self._queue.enqueue(task, scheduled_at)
        return task

    def submit_tasks(self, tasks: Iterable[TaskSpec]) -> List[TaskSpec]:
        ordered = sorted(tasks, key=lambda task: task.task_id)
        results: List[TaskSpec] = []
        for task in ordered:
            submitted = self.submit_task(task)
            if submitted is not None:
                results.append(submitted)
        return results
