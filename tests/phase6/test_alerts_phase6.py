from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from services.alerts.dispatchers import DispatchResult
from services.alerts.repository import AlertRepository
from services.alerts.service import AlertService
from services.common.enums import AlertChannel
from services.dedupe.models import ListingChange
from services.dedupe.service import ListingChangeStore
from services.ranking.service import RankingService
from services.retrieval.models import ListingDocument
from services.retrieval.repository import ListingRepository
from services.retrieval.service import RetrievalConfig, RetrievalService
from services.searchspec.parser import SearchSpecParser
from services.searchspec.repository import SearchSpecRepository
from services.searchspec.service import SearchSpecService


FIXED_TIME = datetime(2026, 1, 28, tzinfo=timezone.utc)


def test_alerts_api_run_and_dispatch():
    import services.alerts.app as alerts_app

    class StubDispatcher:
        def send(self, alert):
            return DispatchResult(success=True)

    listing_repo = ListingRepository()
    listing_repo.add(
        ListingDocument(
            listing_id="list-1",
            building_id="b1",
            neighborhood="mission",
            source_id="s1",
            title="Two bed",
            body="Laundry",
        )
    )
    alerts_app._listing_repo = listing_repo
    alerts_app._retrieval = RetrievalService(listing_repo, config=RetrievalConfig())
    alerts_app._ranking = RankingService(listings=listing_repo, retrieval=alerts_app._retrieval)
    listing_changes = ListingChangeStore()
    listing_changes.record(
        ListingChange(
            change_id="chg-1",
            listing_id="list-1",
            field_path="/listing/title",
            old_value_json="Old",
            new_value_json="Two bed",
            changed_at=FIXED_TIME,
        )
    )
    alerts_app._listing_changes = listing_changes

    search_repo = SearchSpecRepository()
    search_service = SearchSpecService(search_repo, parser=SearchSpecParser(known_neighborhoods={"mission"}))
    created = search_service.create_from_payload(
        {
            "schema_version": "v1",
            "search_spec_id": "spec-alerts",
            "created_at": FIXED_TIME.isoformat(),
            "raw_prompt": "two bed",
        }
    )
    assert created.record is not None
    alerts_app._searchspec_repo = search_repo
    alerts_app._searchspec_service = search_service

    alert_repo = AlertRepository()
    alert_service = AlertService(
        alert_repo,
        search_service,
        alerts_app._ranking,
        listing_repo,
        listing_changes,
        dispatchers={AlertChannel.local: StubDispatcher()},
        clock=lambda: FIXED_TIME,
    )
    alerts_app._alert_repo = alert_repo
    alerts_app._alert_service = alert_service
    alerts_app._dispatchers = {AlertChannel.local: StubDispatcher()}

    client = TestClient(alerts_app.app)
    response = client.post(
        "/alerts/run",
        json={
            "schema_version": "v1",
            "search_spec_id": created.record.spec.search_spec_id,
            "since": (FIXED_TIME - timedelta(days=1)).isoformat(),
        },
    )
    payload = response.json()
    assert payload["schema_version"] == "v1"
    assert payload["status"] == "ok"
    assert payload["data"]["alerts_created"] == 1

    alert_ids = [record.alert_id for record in alert_repo.list()]
    dispatch = client.post(
        "/alerts/dispatch",
        json={"schema_version": "v1", "alert_ids": alert_ids, "channel": "local"},
    ).json()
    assert dispatch["status"] == "ok"
    assert dispatch["data"]["dispatched"] == 1

    repeat = client.post(
        "/alerts/dispatch",
        json={"schema_version": "v1", "alert_ids": alert_ids, "channel": "local"},
    ).json()
    assert repeat["data"]["dispatched"] == 0
