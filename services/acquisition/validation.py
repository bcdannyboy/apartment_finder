from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Iterable, Tuple

from pydantic import ValidationError

from services.acquisition.errors import QueuePayloadError, TaskValidationError
from services.acquisition.models import TaskSchema, TaskSpec
from services.common.enums import TaskType


ALLOWED_FORMATS = {"html", "markdown", "screenshot"}
FIRECRAWL_TASKS = {TaskType.CrawlTask, TaskType.ScrapeTask}


def validate_task_schema(payload: Dict[str, Any]) -> TaskSpec:
    try:
        schema = TaskSchema(**payload)
    except ValidationError as exc:
        raise TaskValidationError(str(exc)) from exc
    data = schema.model_dump()
    return TaskSpec(**data)


def _validate_formats(formats: Dict[str, Any]) -> None:
    unknown = set(formats.keys()) - ALLOWED_FORMATS
    if unknown:
        raise QueuePayloadError(f"Unsupported format field(s): {sorted(unknown)}")


def validate_queue_payload(task: TaskSpec) -> None:
    if not task.policy_id:
        raise QueuePayloadError("policy_id is required before enqueue")
    if not task.domain:
        raise QueuePayloadError("domain is required before enqueue")

    if task.task_type in FIRECRAWL_TASKS:
        payload = task.payload or {}
        formats = payload.get("formats")
        if not isinstance(formats, dict):
            raise QueuePayloadError("payload.formats is required for Firecrawl tasks")
        _validate_formats(formats)
        if "change_tracking" not in payload or payload.get("change_tracking") is None:
            raise QueuePayloadError("payload.change_tracking is required for Firecrawl tasks")
        if not formats.get("markdown"):
            raise QueuePayloadError("change_tracking requires markdown format")


def serialize_task(task: TaskSpec) -> Dict[str, Any]:
    payload = asdict(task)
    payload["task_type"] = task.task_type.value
    payload["status"] = task.status.value
    payload["scheduled_at"] = task.scheduled_at.isoformat()
    payload["created_at"] = task.created_at.isoformat()
    return payload


def collect_task_ids(tasks: Iterable[TaskSpec]) -> Tuple[str, ...]:
    return tuple(task.task_id for task in tasks)
