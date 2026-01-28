from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from uuid import uuid4

from services.common.enums import AlertChannel


@dataclass(frozen=True)
class AlertRecord:
    alert_id: str
    search_spec_id: str
    listing_id: str
    created_at: datetime


class AlertRepository:
    def __init__(self) -> None:
        self._alerts: Dict[str, AlertRecord] = {}
        self._by_key: Dict[Tuple[str, str], str] = {}
        self._dispatch_log: Set[Tuple[str, AlertChannel]] = set()

    def add(
        self,
        *,
        search_spec_id: str,
        listing_id: str,
        created_at: datetime,
    ) -> tuple[AlertRecord, bool]:
        key = (search_spec_id, listing_id)
        existing_id = self._by_key.get(key)
        if existing_id:
            return self._alerts[existing_id], False
        record = AlertRecord(
            alert_id=str(uuid4()),
            search_spec_id=search_spec_id,
            listing_id=listing_id,
            created_at=created_at,
        )
        self._alerts[record.alert_id] = record
        self._by_key[key] = record.alert_id
        return record, True

    def get(self, alert_id: str) -> Optional[AlertRecord]:
        return self._alerts.get(alert_id)

    def list(self) -> List[AlertRecord]:
        return list(self._alerts.values())

    def mark_dispatched(self, alert_id: str, channel: AlertChannel) -> bool:
        key = (alert_id, channel)
        if key in self._dispatch_log:
            return False
        self._dispatch_log.add(key)
        return True
