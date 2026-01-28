from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Mapping, Optional

from services.alerts.dispatchers import AlertChannelAdapter, AlertDispatchError, DispatchResult
from services.alerts.repository import AlertRepository
from services.alerts.repository import MatchLogEntry
from services.alerts.models import DispatchStatus
from services.common.enums import AlertChannel
from services.dedupe.service import ListingChangeStore
from services.ranking.service import RankingService
from services.retrieval.repository import ListingRepository
from services.searchspec.service import SearchSpecService


class AlertService:
    def __init__(
        self,
        repository: AlertRepository,
        searchspec_service: SearchSpecService,
        ranking_service: RankingService,
        listing_repo: ListingRepository,
        listing_changes: ListingChangeStore,
        *,
        dispatchers: Optional[Mapping[AlertChannel, AlertChannelAdapter]] = None,
        clock: Optional[Callable[[], datetime]] = None,
        alert_limit: int = 50,
        max_attempts: int = 3,
    ) -> None:
        self._repository = repository
        self._searchspec_service = searchspec_service
        self._ranking_service = ranking_service
        self._listing_repo = listing_repo
        self._listing_changes = listing_changes
        self._dispatchers = dispatchers or {}
        self._clock = clock or (lambda: datetime.now(tz=timezone.utc))
        self._alert_limit = alert_limit
        self._max_attempts = max_attempts

    def run(self, *, search_spec_id: str, since: datetime) -> int:
        spec = self._searchspec_service.get(search_spec_id)
        if spec is None:
            raise KeyError("searchspec not found")
        created = 0
        now = self._clock()
        changes = sorted(self._listing_changes.list(), key=lambda item: (item.changed_at, item.change_id))
        for change in changes:
            if change.changed_at < since:
                self._repository.record_match(
                    MatchLogEntry(
                        listing_change_id=change.change_id,
                        listing_id=change.listing_id,
                        search_spec_id=search_spec_id,
                        status="skipped",
                        reasons=["before_since"],
                        created_at=now,
                    )
                )
                continue
            if not change.change_id or not change.listing_id:
                self._repository.record_match(
                    MatchLogEntry(
                        listing_change_id=change.change_id,
                        listing_id=change.listing_id,
                        search_spec_id=search_spec_id,
                        status="skipped",
                        reasons=["invalid_listing_change"],
                        created_at=now,
                    )
                )
                continue
            listing = self._listing_repo.get(change.listing_id)
            if listing is None:
                self._repository.record_match(
                    MatchLogEntry(
                        listing_change_id=change.change_id,
                        listing_id=change.listing_id,
                        search_spec_id=search_spec_id,
                        status="skipped",
                        reasons=["listing_missing"],
                        created_at=now,
                    )
                )
                continue
            passes, flags = self._ranking_service.evaluate_hard_constraints(listing, spec)
            if not passes:
                self._repository.record_match(
                    MatchLogEntry(
                        listing_change_id=change.change_id,
                        listing_id=change.listing_id,
                        search_spec_id=search_spec_id,
                        status="filtered",
                        reasons=flags or ["hard_constraints_failed"],
                        created_at=now,
                    )
                )
                continue
            _, is_new = self._repository.add(
                search_spec_id=search_spec_id,
                listing_id=change.listing_id,
                listing_change_id=change.change_id,
                created_at=now,
            )
            self._repository.record_match(
                MatchLogEntry(
                    listing_change_id=change.change_id,
                    listing_id=change.listing_id,
                    search_spec_id=search_spec_id,
                    status="matched",
                    reasons=flags,
                    created_at=now,
                )
            )
            if is_new:
                created += 1
            if created >= self._alert_limit:
                break
        return created

    def dispatch(self, *, alert_ids: list[str], channel: AlertChannel | str) -> int:
        normalized_channel = self._normalize_channel(channel)
        dispatched = 0
        now = self._clock()
        dispatcher = self._dispatchers.get(normalized_channel)
        for alert_id in alert_ids:
            alert = self._repository.get(alert_id)
            if alert is None:
                continue
            payload_hash = self._repository.payload_hash(alert, normalized_channel)
            reservation = self._repository.reserve_dispatch(
                alert=alert,
                channel=normalized_channel,
                payload_hash=payload_hash,
                created_at=now,
                max_attempts=self._max_attempts,
            )
            if reservation is None:
                continue
            result = self._send_alert(alert, normalized_channel, dispatcher)
            status = self._status_for_result(result, reservation.attempt)
            final_status = self._repository.record_dispatch_result(
                alert=alert,
                channel=normalized_channel,
                payload_hash=payload_hash,
                reservation=reservation,
                status=status,
                error=None if status == DispatchStatus.succeeded else result.error,
                created_at=now,
            )
            if final_status == DispatchStatus.succeeded:
                dispatched += 1
        return dispatched

    def _normalize_channel(self, channel: AlertChannel | str) -> AlertChannel:
        if isinstance(channel, AlertChannel):
            return channel
        try:
            return AlertChannel(channel)
        except ValueError as exc:
            raise ValueError("Unsupported alert channel") from exc

    def _send_alert(
        self,
        alert,
        channel: AlertChannel,
        dispatcher: Optional[AlertChannelAdapter],
    ) -> DispatchResult:
        if dispatcher is None:
            return DispatchResult(success=False, retryable=True, error="dispatcher_missing")
        try:
            return dispatcher.send(alert)
        except AlertDispatchError as exc:
            return DispatchResult(success=False, retryable=exc.retryable, error=str(exc))
        except Exception as exc:  # pragma: no cover - defensive guard
            return DispatchResult(success=False, retryable=False, error=str(exc))

    def _status_for_result(self, result: DispatchResult, attempt: int) -> DispatchStatus:
        if result.success:
            return DispatchStatus.succeeded
        if result.retryable and attempt < self._max_attempts:
            return DispatchStatus.retrying
        return DispatchStatus.failed
