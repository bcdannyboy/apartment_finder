from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel

from services.common.enums import TaskType


class TaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    denied = "denied"


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class TaskSchema(BaseModel):
    task_id: str
    task_type: TaskType
    source_id: str
    policy_id: str
    domain: str
    payload: Dict[str, Any]
    status: TaskStatus
    attempt: int
    max_attempts: int
    scheduled_at: datetime
    created_at: datetime


@dataclass
class TaskSpec:
    task_id: str
    task_type: TaskType
    source_id: str
    policy_id: str
    domain: str
    payload: Dict[str, Any]
    status: TaskStatus = TaskStatus.queued
    attempt: int = 0
    max_attempts: int = 3
    scheduled_at: datetime = field(default_factory=_now)
    created_at: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class TaskTransition:
    task_id: str
    from_status: TaskStatus
    to_status: TaskStatus
    changed_at: datetime


@dataclass(frozen=True)
class AuditLogRecord:
    audit_id: str
    task_id: str
    policy_id: Optional[str]
    outcome: str
    params: Dict[str, Any]
    error_class: Optional[str]
    attempt: int
    source_id: Optional[str]
    domain: Optional[str]
    created_at: datetime


class FirecrawlRequest(BaseModel):
    schema_version: str
    url: str
    formats: Dict[str, Any]
    change_tracking: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class FirecrawlResponse(BaseModel):
    url: str
    http_status: int
    formats: Dict[str, Any]
    fetched_at: str
    content_hash: Optional[str] = None
    change_tracking: Optional[Dict[str, Any]] = None
    storage_refs: Optional[Dict[str, Any]] = None
    raw_content: Optional[str] = None


@dataclass(frozen=True)
class AdapterLogRecord:
    log_id: str
    task_id: Optional[str]
    request: Dict[str, Any]
    response: Optional[Dict[str, Any]]
    created_at: datetime
