from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from services.alerts.repository import AlertRepository
from services.common.enums import AlertChannel
from services.ranking.service import RankingService
from services.searchspec.service import SearchSpecService


class AlertService:
    def __init__(
        self,
        repository: AlertRepository,
        searchspec_service: SearchSpecService,
        ranking_service: RankingService,
        *,
        clock: Optional[Callable[[], datetime]] = None,
        alert_limit: int = 50,
    ) -> None:
        self._repository = repository
        self._searchspec_service = searchspec_service
        self._ranking_service = ranking_service
        self._clock = clock or (lambda: datetime.now(tz=timezone.utc))
        self._alert_limit = alert_limit

    def run(self, *, search_spec_id: str, since: datetime) -> int:
        spec = self._searchspec_service.get(search_spec_id)
        if spec is None:
            raise KeyError("searchspec not found")
        results = self._ranking_service.rank(spec, limit=self._alert_limit).results
        created = 0
        now = self._clock()
        for result in results:
            _, is_new = self._repository.add(
                search_spec_id=search_spec_id,
                listing_id=result.listing_id,
                created_at=now,
            )
            if is_new and now >= since:
                created += 1
        return created

    def dispatch(self, *, alert_ids: list[str], channel: AlertChannel) -> int:
        dispatched = 0
        for alert_id in alert_ids:
            if self._repository.get(alert_id) is None:
                continue
            if self._repository.mark_dispatched(alert_id, channel):
                dispatched += 1
        return dispatched
