from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from services.alerts.models import DispatchStatus
from services.common.enums import AlertChannel
from services.dedupe.determinism import stable_hash
from services.extraction.determinism import deterministic_id


@dataclass(frozen=True)
class AlertRecord:
    alert_id: str
    search_spec_id: str
    listing_id: str
    listing_change_id: str
    created_at: datetime


@dataclass(frozen=True)
class DispatchLogEntry:
    dispatch_id: str
    alert_id: str
    listing_change_id: str
    search_spec_id: str
    channel: AlertChannel
    payload_hash: str
    idempotency_key: str
    status: DispatchStatus
    attempt: int
    error: Optional[str]
    created_at: datetime


@dataclass(frozen=True)
class MatchLogEntry:
    listing_change_id: str
    listing_id: str
    search_spec_id: str
    status: str
    reasons: List[str]
    created_at: datetime


@dataclass
class DispatchState:
    attempts: int = 0
    succeeded: bool = False
    terminal_failure: bool = False


@dataclass(frozen=True)
class DispatchReservation:
    idempotency_key: str
    attempt: int


class AlertRepository:
    def __init__(self) -> None:
        self._alerts: Dict[str, AlertRecord] = {}
        self._by_key: Dict[Tuple[str, str], str] = {}
        self._dispatch_log: List[DispatchLogEntry] = []
        self._dispatch_state: Dict[str, DispatchState] = {}
        self._match_log: List[MatchLogEntry] = []

    def add(
        self,
        *,
        search_spec_id: str,
        listing_id: str,
        listing_change_id: str,
        created_at: datetime,
    ) -> tuple[AlertRecord, bool]:
        key = (search_spec_id, listing_change_id)
        existing_id = self._by_key.get(key)
        if existing_id:
            return self._alerts[existing_id], False
        record = AlertRecord(
            alert_id=deterministic_id(
                "alert",
                {"search_spec_id": search_spec_id, "listing_change_id": listing_change_id},
            ),
            search_spec_id=search_spec_id,
            listing_id=listing_id,
            listing_change_id=listing_change_id,
            created_at=created_at,
        )
        self._alerts[record.alert_id] = record
        self._by_key[key] = record.alert_id
        return record, True

    def get(self, alert_id: str) -> Optional[AlertRecord]:
        return self._alerts.get(alert_id)

    def list(self) -> List[AlertRecord]:
        return list(self._alerts.values())

    def record_match(self, entry: MatchLogEntry) -> None:
        self._match_log.append(entry)

    def match_logs(self) -> List[MatchLogEntry]:
        return list(self._match_log)

    def dispatch_logs(self) -> List[DispatchLogEntry]:
        return list(self._dispatch_log)

    def idempotency_key(self, alert_id: str, channel: AlertChannel) -> str:
        return f"{alert_id}:{channel.value}"

    def payload_hash(self, alert: AlertRecord, channel: AlertChannel) -> str:
        payload = {
            "alert_id": alert.alert_id,
            "listing_id": alert.listing_id,
            "listing_change_id": alert.listing_change_id,
            "search_spec_id": alert.search_spec_id,
            "channel": channel.value,
        }
        return stable_hash(payload)

    def reserve_dispatch(
        self,
        *,
        alert: AlertRecord,
        channel: AlertChannel,
        payload_hash: str,
        created_at: datetime,
        max_attempts: int,
    ) -> Optional[DispatchReservation]:
        key = self.idempotency_key(alert.alert_id, channel)
        state = self._dispatch_state.setdefault(key, DispatchState())
        if state.succeeded or state.terminal_failure or state.attempts >= max_attempts:
            return None
        state.attempts += 1
        attempt = state.attempts
        dispatch_id = deterministic_id(
            "dispatch",
            {"idempotency_key": key, "attempt": attempt, "event": "attempt"},
        )
        self._dispatch_log.append(
            DispatchLogEntry(
                dispatch_id=dispatch_id,
                alert_id=alert.alert_id,
                listing_change_id=alert.listing_change_id,
                search_spec_id=alert.search_spec_id,
                channel=channel,
                payload_hash=payload_hash,
                idempotency_key=key,
                status=DispatchStatus.pending,
                attempt=attempt,
                error=None,
                created_at=created_at,
            )
        )
        return DispatchReservation(idempotency_key=key, attempt=attempt)

    def record_dispatch_result(
        self,
        *,
        alert: AlertRecord,
        channel: AlertChannel,
        payload_hash: str,
        reservation: DispatchReservation,
        status: DispatchStatus,
        error: Optional[str],
        created_at: datetime,
    ) -> DispatchStatus:
        state = self._dispatch_state.setdefault(reservation.idempotency_key, DispatchState())
        if status == DispatchStatus.succeeded:
            state.succeeded = True
        elif status == DispatchStatus.failed:
            state.terminal_failure = True
        dispatch_id = deterministic_id(
            "dispatch",
            {
                "idempotency_key": reservation.idempotency_key,
                "attempt": reservation.attempt,
                "event": "result",
                "status": status.value,
            },
        )
        self._dispatch_log.append(
            DispatchLogEntry(
                dispatch_id=dispatch_id,
                alert_id=alert.alert_id,
                listing_change_id=alert.listing_change_id,
                search_spec_id=alert.search_spec_id,
                channel=channel,
                payload_hash=payload_hash,
                idempotency_key=reservation.idempotency_key,
                status=status,
                attempt=reservation.attempt,
                error=error,
                created_at=created_at,
            )
        )
        return status
