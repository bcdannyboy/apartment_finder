from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from services.phase8.fixtures import get_phase8_fixtures
from services.ui.app import app


client = TestClient(app)


def test_ui_serves_spa_and_uses_api_calls():
    response = client.get("/")
    assert response.status_code == 200
    assert "Apartment Finder" in response.text

    js_path = Path("services/ui/static/app.js")
    content = js_path.read_text()
    assert "fetch" in content
    assert "/api" in content
    assert "postgres" not in content
    assert "psycopg" not in content


def test_ui_listings_evidence_and_missing_markers():
    fixtures = get_phase8_fixtures()
    response = client.get("/api/listings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    listings = payload["data"]["listings"]
    assert listings

    alpha_id = fixtures.listings[0].listing_id
    bravo_id = fixtures.listings[1].listing_id

    alpha = next(item for item in listings if item["listing_id"] == alpha_id)
    for field in alpha["fields"].values():
        assert field["evidence"], "Expected evidence for alpha fields"
        assert field["missing_evidence"] is False

    bravo = next(item for item in listings if item["listing_id"] == bravo_id)
    deposit_field = bravo["fields"]["deposit"]
    assert deposit_field["missing_evidence"] is True


def test_ui_detail_and_history_include_evidence():
    fixtures = get_phase8_fixtures()
    listing_id = fixtures.listings[0].listing_id

    detail = client.get(f"/api/listings/{listing_id}")
    assert detail.status_code == 200
    listing = detail.json()["data"]["listing"]
    for field in listing["fields"].values():
        assert "evidence" in field

    history = client.get(f"/api/listings/{listing_id}/history")
    assert history.status_code == 200
    entries = history.json()["data"]["history"]
    assert entries
    timestamps = [entry["changed_at"] for entry in entries]
    assert timestamps == sorted(timestamps)
    for entry in entries:
        assert entry["evidence"], "History entries must include evidence"


def test_ui_compare_validation_and_snapshot_guardrails():
    fixtures = get_phase8_fixtures()
    left = fixtures.listings[0]
    right = fixtures.listings[1]

    bad = client.post("/api/compare", json={"schema_version": "v1"})
    assert bad.status_code == 400

    bad_id = client.post(
        "/api/compare",
        json={
            "schema_version": "v1",
            "listing_id_left": "not-a-uuid",
            "listing_id_right": "still-not",
        },
    )
    assert bad_id.status_code == 400

    mismatch = client.post(
        "/api/compare",
        json={
            "schema_version": "v1",
            "listing_id_left": left.listing_id,
            "listing_id_right": right.listing_id,
            "snapshot_id_left": right.snapshot_id,
        },
    )
    assert mismatch.status_code == 400


def test_ui_near_miss_validation_and_response():
    fixtures = get_phase8_fixtures()
    spec_id = fixtures.search_specs[1].search_spec_id

    bad = client.post("/api/near-miss", json={"schema_version": "v1", "search_spec_id": spec_id})
    assert bad.status_code == 400

    bad_threshold = client.post(
        "/api/near-miss",
        json={"schema_version": "v1", "search_spec_id": spec_id, "threshold": 2},
    )
    assert bad_threshold.status_code == 400

    good = client.post(
        "/api/near-miss",
        json={"schema_version": "v1", "search_spec_id": spec_id, "threshold": 0.2},
    )
    assert good.status_code == 200
    results = good.json()["data"]["near_miss"]
    assert results
    assert "price" in results[0]
