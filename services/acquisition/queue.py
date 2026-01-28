from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional, Protocol

from services.acquisition.models import TaskSpec


@dataclass(frozen=True)
class QueueItem:
    job_id: str
    task_id: str
    scheduled_at: datetime


class QueueBackend(Protocol):
    def enqueue(self, task: TaskSpec, scheduled_at: datetime) -> str: ...

    def list(self) -> List[QueueItem]: ...

    def pop_due(self, now: datetime) -> List[QueueItem]: ...


class InMemoryQueueAdapter:
    def __init__(self) -> None:
        self._items: List[QueueItem] = []

    def enqueue(self, task: TaskSpec, scheduled_at: datetime) -> str:
        job_id = task.task_id
        self._items.append(
            QueueItem(job_id=job_id, task_id=task.task_id, scheduled_at=scheduled_at)
        )
        self._items.sort(key=lambda item: (item.scheduled_at, item.task_id))
        return job_id

    def list(self) -> List[QueueItem]:
        return list(self._items)

    def pop_due(self, now: datetime) -> List[QueueItem]:
        due: List[QueueItem] = []
        remaining: List[QueueItem] = []
        for item in self._items:
            if item.scheduled_at <= now:
                due.append(item)
            else:
                remaining.append(item)
        self._items = remaining
        return due


class RQQueueAdapter:
    def __init__(
        self,
        *,
        queue_name: str,
        connection,
        job_handler: Optional[Callable[..., object]] = None,
    ) -> None:
        from rq import Queue

        self._queue = Queue(name=queue_name, connection=connection)
        self._job_handler = job_handler

    def enqueue(self, task: TaskSpec, scheduled_at: datetime) -> str:
        if self._job_handler is None:
            raise ValueError("job_handler is required for RQ enqueue")
        job = self._queue.enqueue_at(scheduled_at, self._job_handler, task.task_id)
        return job.id

    def list(self) -> List[QueueItem]:
        jobs = self._queue.get_jobs()
        return [
            QueueItem(
                job_id=job.id,
                task_id=str(job.args[0]) if job.args else job.id,
                scheduled_at=job.enqueued_at or job.created_at,
            )
            for job in jobs
        ]

    def pop_due(self, now: datetime) -> List[QueueItem]:
        raise NotImplementedError("Use rq.Worker to consume jobs")
