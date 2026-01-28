from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from services.alerts.dispatchers import DispatchResult
from services.alerts.models import DispatchStatus
from services.alerts.repository import AlertRepository
from services.alerts.service import AlertService
from services.common.enums import AlertChannel
from services.dedupe.models import ListingChange
from services.dedupe.service import ListingChangeStore
from services.ranking.service import RankingService
from services.retrieval.models import FieldValue, ListingDocument
from services.retrieval.repository import ListingRepository
from services.retrieval.service import RetrievalConfig, RetrievalService
from services.searchspec.parser import SearchSpecParser
from services.searchspec.repository import SearchSpecRepository
from services.searchspec.service import SearchSpecService


FIXED_TIME = datetime(2026, 1, 28, tzinfo=timezone.utc)


class SequenceDispatcher:
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def send(self, alert):
        result = self._results[min(self.calls, len(self._results) - 1)]
        self.calls += 1
        return result


def _make_services():
    listing_repo = ListingRepository()
    retrieval = RetrievalService(listing_repo, config=RetrievalConfig())
    ranking = RankingService(listings=listing_repo, retrieval=retrieval)
    search_repo = SearchSpecRepository()
    search_service = SearchSpecService(search_repo, parser=SearchSpecParser(known_neighborhoods={"mission"}))
    return listing_repo, ranking, search_service


def test_alert_matching_respects_hard_constraints():
    listing_repo, ranking, search_service = _make_services()
    listing_repo.add(
        ListingDocument(
            listing_id="list-pass",
            building_id="b1",
            neighborhood="mission",
            source_id="s1",
            title="Two bed",
            body="Updated",
            structured={"beds": FieldValue(value=2, confidence=0.9)},
        )
    )
    listing_repo.add(
        ListingDocument(
            listing_id="list-fail",
            building_id="b2",
            neighborhood="mission",
            source_id="s1",
            title="One bed",
            body="Updated",
            structured={"beds": FieldValue(value=1, confidence=0.9)},
        )
    )
    listing_changes = ListingChangeStore()
    listing_changes.record(
        ListingChange(
            change_id="chg-pass",
            listing_id="list-pass",
            field_path="/units/beds",
            old_value_json=1,
            new_value_json=2,
            changed_at=FIXED_TIME,
        )
    )
    listing_changes.record(
        ListingChange(
            change_id="chg-fail",
            listing_id="list-fail",
            field_path="/units/beds",
            old_value_json=2,
            new_value_json=1,
            changed_at=FIXED_TIME,
        )
    )
    created = search_service.create_from_payload(
        {
            "schema_version": "v1",
            "search_spec_id": "spec-hard",
            "created_at": FIXED_TIME.isoformat(),
            "raw_prompt": "two bed",
            "hard": {"beds_min": 2},
        }
    )
    assert created.record is not None
    alert_repo = AlertRepository()
    service = AlertService(
        alert_repo,
        search_service,
        ranking,
        listing_repo,
        listing_changes,
        clock=lambda: FIXED_TIME,
    )
    created_count = service.run(
        search_spec_id=created.record.spec.search_spec_id,
        since=FIXED_TIME - timedelta(days=1),
    )
    assert created_count == 1
    alerts = alert_repo.list()
    assert len(alerts) == 1
    assert alerts[0].listing_id == "list-pass"
    match_logs = alert_repo.match_logs()
    fail_log = next(entry for entry in match_logs if entry.listing_change_id == "chg-fail")
    assert fail_log.status == "filtered"
    assert any("beds" in reason for reason in fail_log.reasons)


def test_alert_run_idempotent_per_listing_change():
    listing_repo, ranking, search_service = _make_services()
    listing_repo.add(
        ListingDocument(
            listing_id="list-1",
            building_id="b1",
            neighborhood="mission",
            source_id="s1",
            title="Studio",
            body="Updated",
        )
    )
    listing_changes = ListingChangeStore()
    listing_changes.record(
        ListingChange(
            change_id="chg-1",
            listing_id="list-1",
            field_path="/listing/title",
            old_value_json="Old",
            new_value_json="Studio",
            changed_at=FIXED_TIME,
        )
    )
    created = search_service.create_from_payload(
        {
            "schema_version": "v1",
            "search_spec_id": "spec-idempotent",
            "created_at": FIXED_TIME.isoformat(),
            "raw_prompt": "studio",
        }
    )
    assert created.record is not None
    alert_repo = AlertRepository()
    service = AlertService(
        alert_repo,
        search_service,
        ranking,
        listing_repo,
        listing_changes,
        clock=lambda: FIXED_TIME,
    )
    first = service.run(
        search_spec_id=created.record.spec.search_spec_id,
        since=FIXED_TIME - timedelta(days=1),
    )
    second = service.run(
        search_spec_id=created.record.spec.search_spec_id,
        since=FIXED_TIME - timedelta(days=1),
    )
    assert first == 1
    assert second == 0
    assert len(alert_repo.list()) == 1


def test_dispatch_logging_retry_and_success():
    listing_repo, ranking, search_service = _make_services()
    listing_changes = ListingChangeStore()
    alert_repo = AlertRepository()
    alert, _ = alert_repo.add(
        search_spec_id="spec-1",
        listing_id="list-1",
        listing_change_id="chg-1",
        created_at=FIXED_TIME,
    )
    dispatcher = SequenceDispatcher(
        [
            DispatchResult(success=False, retryable=True, error="smtp_timeout"),
            DispatchResult(success=True),
        ]
    )
    service = AlertService(
        alert_repo,
        search_service,
        ranking,
        listing_repo,
        listing_changes,
        dispatchers={AlertChannel.smtp: dispatcher},
        clock=lambda: FIXED_TIME,
        max_attempts=3,
    )
    first = service.dispatch(alert_ids=[alert.alert_id], channel=AlertChannel.smtp)
    second = service.dispatch(alert_ids=[alert.alert_id], channel=AlertChannel.smtp)
    assert first == 0
    assert second == 1
    logs = alert_repo.dispatch_logs()
    assert [entry.status for entry in logs] == [
        DispatchStatus.pending,
        DispatchStatus.retrying,
        DispatchStatus.pending,
        DispatchStatus.succeeded,
    ]
    idempotency_key = alert_repo.idempotency_key(alert.alert_id, AlertChannel.smtp)
    payload_hashes = {entry.payload_hash for entry in logs}
    assert all(entry.idempotency_key == idempotency_key for entry in logs)
    assert len(payload_hashes) == 1
    attempts = [entry.attempt for entry in logs if entry.status != DispatchStatus.pending]
    assert attempts == [1, 2]
    assert logs[1].error == "smtp_timeout"
    with pytest.raises(FrozenInstanceError):
        logs[0].status = DispatchStatus.failed


def test_dispatch_terminal_failure_and_channel_validation():
    listing_repo, ranking, search_service = _make_services()
    listing_changes = ListingChangeStore()
    alert_repo = AlertRepository()
    alert, _ = alert_repo.add(
        search_spec_id="spec-2",
        listing_id="list-2",
        listing_change_id="chg-2",
        created_at=FIXED_TIME,
    )

    class FailDispatcher:
        def send(self, alert):
            return DispatchResult(success=False, retryable=False, error="smtp_bad_recipient")

    service = AlertService(
        alert_repo,
        search_service,
        ranking,
        listing_repo,
        listing_changes,
        dispatchers={AlertChannel.smtp: FailDispatcher()},
        clock=lambda: FIXED_TIME,
        max_attempts=2,
    )
    first = service.dispatch(alert_ids=[alert.alert_id], channel=AlertChannel.smtp)
    second = service.dispatch(alert_ids=[alert.alert_id], channel=AlertChannel.smtp)
    assert first == 0
    assert second == 0
    logs = alert_repo.dispatch_logs()
    assert [entry.status for entry in logs] == [DispatchStatus.pending, DispatchStatus.failed]
    assert logs[1].error == "smtp_bad_recipient"
    with pytest.raises(ValueError):
        service.dispatch(alert_ids=[alert.alert_id], channel="sms")
