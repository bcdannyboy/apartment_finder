from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from services.acquisition.models import AdapterLogRecord, AuditLogRecord, TaskSpec, TaskStatus, TaskTransition


class TaskRepository:
    def __init__(self) -> None:
        self._tasks: Dict[str, TaskSpec] = {}
        self._transitions: List[TaskTransition] = []

    def add(self, task: TaskSpec) -> None:
        self._tasks[task.task_id] = task

    def get(self, task_id: str) -> Optional[TaskSpec]:
        return self._tasks.get(task_id)

    def list(self) -> List[TaskSpec]:
        return list(self._tasks.values())

    def update_status(self, task_id: str, status: TaskStatus, changed_at: datetime) -> None:
        task = self._tasks[task_id]
        from_status = task.status
        task.status = status
        self._transitions.append(
            TaskTransition(
                task_id=task_id,
                from_status=from_status,
                to_status=status,
                changed_at=changed_at,
            )
        )

    def increment_attempt(self, task_id: str) -> int:
        task = self._tasks[task_id]
        task.attempt += 1
        return task.attempt

    def transitions(self) -> List[TaskTransition]:
        return list(self._transitions)

    def serialize_task(self, task_id: str) -> Dict[str, object]:
        task = self._tasks[task_id]
        payload = asdict(task)
        payload["task_type"] = task.task_type.value
        payload["status"] = task.status.value
        payload["scheduled_at"] = task.scheduled_at.isoformat()
        payload["created_at"] = task.created_at.isoformat()
        return payload


class AuditLogRepository:
    def __init__(self) -> None:
        self._records: List[AuditLogRecord] = []

    def add(self, record: AuditLogRecord) -> None:
        self._records.append(record)

    def list(self) -> List[AuditLogRecord]:
        return list(self._records)

    def new_id(self) -> str:
        return str(uuid4())


class AdapterLogRepository:
    def __init__(self) -> None:
        self._records: List[AdapterLogRecord] = []

    def add(self, record: AdapterLogRecord) -> None:
        self._records.append(record)

    def list(self) -> List[AdapterLogRecord]:
        return list(self._records)
