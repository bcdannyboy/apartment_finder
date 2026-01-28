from __future__ import annotations

from typing import List

from pydantic import BaseModel

from services.common.enums import AlertChannel


class AlertsRunRequest(BaseModel):
    schema_version: str
    search_spec_id: str
    since: str


class AlertsDispatchRequest(BaseModel):
    schema_version: str
    alert_ids: List[str]
    channel: AlertChannel
