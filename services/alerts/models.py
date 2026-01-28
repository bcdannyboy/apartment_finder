from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel

from services.common.enums import AlertChannel


class DispatchStatus(str, Enum):
    pending = "pending"
    succeeded = "succeeded"
    retrying = "retrying"
    failed = "failed"


class AlertsRunRequest(BaseModel):
    schema_version: str
    search_spec_id: str
    since: str


class AlertsDispatchRequest(BaseModel):
    schema_version: str
    alert_ids: List[str]
    channel: AlertChannel
