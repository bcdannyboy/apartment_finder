from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from services.acquisition.determinism import dedupe_task_ids, deterministic_task_id
from services.acquisition.models import TaskSpec, TaskStatus
from services.common.enums import TaskType


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class TaskFactory:
    def __init__(self, *, seed: str = "default") -> None:
        self._seed = seed

    def create_task(
        self,
        *,
        task_type: TaskType,
        source_id: str,
        policy_id: str,
        domain: str,
        payload: Dict[str, Any],
        max_attempts: int = 3,
        scheduled_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
    ) -> TaskSpec:
        task_id = deterministic_task_id(
            seed=self._seed,
            task_type=task_type.value,
            source_id=source_id,
            domain=domain,
            payload=payload,
        )
        return TaskSpec(
            task_id=task_id,
            task_type=task_type,
            source_id=source_id,
            policy_id=policy_id,
            domain=domain,
            payload=payload,
            status=TaskStatus.queued,
            attempt=0,
            max_attempts=max_attempts,
            scheduled_at=scheduled_at or _now(),
            created_at=created_at or _now(),
        )

    def dedupe(self, tasks: Iterable[TaskSpec]) -> List[TaskSpec]:
        ordered_ids = dedupe_task_ids(task.task_id for task in tasks)
        lookup = {task.task_id: task for task in tasks}
        return [lookup[task_id] for task_id in ordered_ids]
