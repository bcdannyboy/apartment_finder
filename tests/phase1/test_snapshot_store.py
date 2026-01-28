from typing import Optional

from fastapi.testclient import TestClient

import services.snapshot_store.app as snapshot_app
from services.common.hashes import sha256_text
from services.snapshot_store.models import SnapshotCreateRequest
from services.snapshot_store.repository import SnapshotRepository
from services.snapshot_store.service import SnapshotStoreService


def _create_request(raw_content: Optional[str] = "<html>hi</html>"):
    return SnapshotCreateRequest(
        schema_version="v1",
        source_id="source-1",
        url="https://example.com/listing",
        fetched_at="2026-01-28T00:00:00Z",
        http_status=200,
        formats={"html": True, "markdown": False, "screenshot": False},
        storage_refs={"html": "/tmp/example.html"},
        raw_content=raw_content,
    )


def test_snapshot_create_hash_computed_and_deterministic():
    repo = SnapshotRepository()
    service = SnapshotStoreService(repo)

    request = _create_request("<html>alpha</html>")
    snapshot = service.create_snapshot(request)
    assert snapshot.content_hash == sha256_text("<html>alpha</html>")

    duplicate = service.create_snapshot(_create_request("<html>alpha</html>"))
    assert duplicate.content_hash == snapshot.content_hash
    assert duplicate.snapshot_id != snapshot.snapshot_id


def test_snapshot_requires_content_hash_if_no_raw_content():
    repo = SnapshotRepository()
    service = SnapshotStoreService(repo)

    request = _create_request(raw_content=None)
    request.content_hash = "hash-provided"
    snapshot = service.create_snapshot(request)
    assert snapshot.content_hash == "hash-provided"


def test_snapshot_lookup_by_raw_refs_and_list():
    repo = SnapshotRepository()
    service = SnapshotStoreService(repo)
    snapshot = service.create_snapshot(_create_request("<html>beta</html>"))

    matches = service.find_by_storage_refs({"html": "/tmp/example.html"})
    assert matches
    assert matches[0].snapshot_id == snapshot.snapshot_id
    assert matches[0].storage_refs == snapshot.storage_refs


def test_snapshot_store_api_contract():
    client = TestClient(snapshot_app.app)
    response = client.post(
        "/snapshots",
        json={
            "schema_version": "v1",
            "source_id": "source-1",
            "url": "https://example.com/listing",
            "fetched_at": "2026-01-28T00:00:00Z",
            "http_status": 200,
            "formats": {"html": True, "markdown": True},
            "storage_refs": {"html": "/tmp/example.html"},
            "content_hash": "hash-123",
        },
    )
    payload = response.json()
    assert payload["schema_version"] == "v1"
    assert payload["status"] == "ok"
    snapshot_id = payload["data"]["snapshot_id"]
    assert payload["data"]["content_hash"] == "hash-123"

    fetch = client.get(f"/snapshots/{snapshot_id}")
    fetch_payload = fetch.json()
    assert fetch_payload["schema_version"] == "v1"
    assert fetch_payload["status"] == "ok"
    data = fetch_payload["data"]
    assert data["snapshot_id"] == snapshot_id
    assert data["content_hash"] == "hash-123"
    assert "storage_refs" in data
    assert "raw_refs" in data

    listing = client.get("/snapshots")
    listing_payload = listing.json()
    assert listing_payload["schema_version"] == "v1"
    assert listing_payload["status"] == "ok"
    assert "snapshots" in listing_payload["data"]
