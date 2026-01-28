from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
import pytest

from services.retrieval.models import FieldValue, ListingDocument
from services.retrieval.repository import ListingRepository
from services.retrieval.service import RetrievalConfig, RetrievalQuery, RetrievalService
from services.ranking.models import RankingConfig, StructuredField
from services.ranking.service import RankingService
from services.searchspec.parser import SearchSpecParser
from services.searchspec.repository import SearchSpecRepository
from services.searchspec.service import SearchSpecService


FIXED_TIME = datetime(2026, 1, 28, tzinfo=timezone.utc)


def _base_searchspec():
    return {
        "schema_version": "v1",
        "search_spec_id": "spec-1",
        "created_at": FIXED_TIME.isoformat(),
        "raw_prompt": "bright two bed with laundry",
        "hard": {
            "price_max": 4000,
            "beds_min": 2,
            "baths_min": 1,
            "neighborhoods_include": ["mission"],
            "commute_max": [
                {"target_label": "anchor-1", "mode": "transit", "max_min": 30}
            ],
            "must_have": ["in unit laundry"],
        },
        "soft": {"weights": {"price": 0.5}},
        "exploration": {"pct": 0, "rules": []},
    }


def test_searchspec_parser_validation_and_normalization():
    parser = SearchSpecParser(known_neighborhoods={"mission"})
    payload = _base_searchspec()
    result = parser.parse(payload)
    assert result.spec is not None
    assert result.spec.hard.must_have == ["in_unit_laundry"]

    bad_version = dict(payload)
    bad_version["schema_version"] = "v2"
    result = parser.parse(bad_version)
    assert result.spec is None
    assert any(err["code"] == "schema_version_mismatch" for err in result.errors)

    bad_price = dict(payload)
    bad_price["hard"] = dict(payload["hard"], price_min=5000)
    result = parser.parse(bad_price)
    assert result.spec is None
    assert any("price_min" in err["path"] for err in result.errors)

    bad_neighborhood = dict(payload)
    bad_neighborhood["hard"] = dict(payload["hard"], neighborhoods_include=["unknown"])
    result = parser.parse(bad_neighborhood)
    assert result.spec is None
    assert any(err["code"] == "unknown_neighborhood" for err in result.errors)

    conflict = dict(payload)
    conflict["hard"] = dict(payload["hard"], available_now=True, move_in_after="2026-02-01")
    result = parser.parse(conflict)
    assert result.spec is None
    assert any(err["code"] == "invalid_combination" for err in result.errors)


def test_retrieval_fts_vector_and_audit_layers():
    repo = ListingRepository()
    repo.add(
        ListingDocument(
            listing_id="list-1",
            building_id="b1",
            neighborhood="mission",
            source_id="s1",
            title="Bright two bed",
            body="Laundry included",
            embedding=[1.0, 0.0],
        )
    )
    repo.add(
        ListingDocument(
            listing_id="list-2",
            building_id="b2",
            neighborhood="mission",
            source_id="s2",
            title="Quiet flat",
            body="two bed with laundry",
            embedding=[0.0, 1.0],
        )
    )
    service = RetrievalService(repo, config=RetrievalConfig())
    result = service.retrieve(RetrievalQuery(keywords=["two", "bed"], vector=[1.0, 0.0]), limit=10)
    assert [event.layer for event in result.audit_events] == ["fts", "vector"]
    assert result.candidates[0].listing_id == "list-1"


def test_candidate_limit_before_rerank_and_determinism():
    repo = ListingRepository()
    for idx in range(5):
        repo.add(
            ListingDocument(
                listing_id=f"list-{idx}",
                building_id=f"b{idx}",
                neighborhood="mission",
                source_id="s1",
                title="two bed",
                body="laundry",
            )
        )
    retrieval = RetrievalService(repo, config=RetrievalConfig())
    ranking = RankingService(listings=repo, retrieval=retrieval, config=RankingConfig(candidate_limit=2))
    parser = SearchSpecParser(known_neighborhoods={"mission"})
    spec = parser.parse(_base_searchspec()).spec
    assert spec is not None
    result1 = ranking.rank(spec, limit=5)
    result2 = ranking.rank(spec, limit=5)
    assert len(result1.rerank_payload) <= 2
    assert [item.listing_id for item in result1.results] == [item.listing_id for item in result2.results]


def test_hard_filters_confidence_and_flags():
    repo = ListingRepository()
    repo.add(
        ListingDocument(
            listing_id="list-high",
            building_id="b1",
            neighborhood="mission",
            source_id="s1",
            title="two bed",
            body="laundry",
            structured={
                "price": FieldValue(value=5000, confidence=0.9),
                "beds": FieldValue(value=2, confidence=0.9),
                "baths": FieldValue(value=1, confidence=0.9),
            },
        )
    )
    repo.add(
        ListingDocument(
            listing_id="list-low",
            building_id="b2",
            neighborhood="mission",
            source_id="s1",
            title="two bed",
            body="laundry",
            structured={
                "price": FieldValue(value=5000, confidence=0.4),
                "beds": FieldValue(value=2, confidence=0.9),
                "baths": FieldValue(value=1, confidence=0.9),
            },
        )
    )
    retrieval = RetrievalService(repo, config=RetrievalConfig())
    ranking = RankingService(listings=repo, retrieval=retrieval, config=RankingConfig())
    parser = SearchSpecParser(known_neighborhoods={"mission"})
    spec = parser.parse(_base_searchspec()).spec
    assert spec is not None
    result = ranking.rank(spec, limit=10)
    listing_ids = [item.listing_id for item in result.results]
    assert "list-high" not in listing_ids
    assert "list-low" in listing_ids
    flags = [item.explanation.flags for item in result.results if item.listing_id == "list-low"][0]
    assert any("price" in flag for flag in flags)


def test_diversity_caps_by_building():
    repo = ListingRepository()
    for idx in range(4):
        repo.add(
            ListingDocument(
                listing_id=f"list-{idx}",
                building_id="b1",
                neighborhood="mission",
                source_id="s1",
                title="two bed",
                body="laundry",
            )
        )
    retrieval = RetrievalService(repo, config=RetrievalConfig())
    ranking = RankingService(listings=repo, retrieval=retrieval, config=RankingConfig())
    parser = SearchSpecParser(known_neighborhoods={"mission"})
    spec = parser.parse(_base_searchspec()).spec
    assert spec is not None
    result = ranking.rank(spec, limit=10)
    assert len(result.results) == ranking._config.diversity_caps.per_building


def test_ranking_api_contract(monkeypatch):
    import services.ranking.app as ranking_app

    listing_repo = ListingRepository()
    listing_repo.add(
        ListingDocument(
            listing_id="list-1",
            building_id="b1",
            neighborhood="mission",
            source_id="s1",
            title="two bed",
            body="laundry",
        )
    )
    ranking_app._listing_repo = listing_repo
    ranking_app._retrieval = RetrievalService(listing_repo, config=RetrievalConfig())
    ranking_app._service = RankingService(listings=listing_repo, retrieval=ranking_app._retrieval)

    search_repo = SearchSpecRepository()
    service = SearchSpecService(search_repo, parser=SearchSpecParser(known_neighborhoods={"mission"}))
    payload = _base_searchspec()
    created = service.create_from_payload(payload)
    assert created.record is not None
    ranking_app._searchspec_repo = search_repo
    ranking_app._searchspec_service = service

    client = TestClient(ranking_app.app)
    response = client.post(
        "/rank",
        json={"schema_version": "v1", "search_spec_id": created.record.spec.search_spec_id, "options": {"limit": 5}},
    )
    data = response.json()
    assert data["schema_version"] == "v1"
    assert data["status"] == "ok"
    assert "results" in data["data"]


def test_rerank_payload_constraints():
    repo = ListingRepository()
    fields = {f"field_{idx}": FieldValue(value=idx, confidence=0.9) for idx in range(50)}
    repo.add(
        ListingDocument(
            listing_id="list-1",
            building_id="b1",
            neighborhood="mission",
            source_id="s1",
            title="two bed",
            body="laundry",
            structured=fields,
        )
    )
    retrieval = RetrievalService(repo, config=RetrievalConfig())
    ranking = RankingService(listings=repo, retrieval=retrieval, config=RankingConfig(max_fields_for_rerank=10))
    parser = SearchSpecParser(known_neighborhoods={"mission"})
    spec = parser.parse(_base_searchspec()).spec
    assert spec is not None
    result = ranking.rank(spec, limit=10)
    assert len(result.rerank_payload[0]["fields"]) == 10
    assert all("title" not in field for field in result.rerank_payload[0].keys())
