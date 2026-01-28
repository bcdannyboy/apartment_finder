from __future__ import annotations

import os
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from services.common.api import error_response, ok_response
from services.phase8.fixtures import get_phase8_fixtures


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="UI", docs_url=None, redoc_url=None)
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


class CompareRequest(BaseModel):
    schema_version: str = Field("v1")
    listing_id_left: Optional[str] = None
    listing_id_right: Optional[str] = None
    snapshot_id_left: Optional[str] = None
    snapshot_id_right: Optional[str] = None


class NearMissRequest(BaseModel):
    schema_version: str = Field("v1")
    search_spec_id: Optional[str] = None
    threshold: Optional[float] = None


def _is_uuid(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def _field_payload(field, evidence_lookup):
    evidence_payloads = []
    for evidence_id in field.evidence_ids:
        evidence = evidence_lookup.get(evidence_id)
        if not evidence:
            continue
        evidence_payloads.append(
            {
                "evidence_id": evidence.evidence_id,
                "snapshot_id": evidence.snapshot_id,
                "kind": evidence.kind,
                "locator": evidence.locator,
                "excerpt": evidence.excerpt,
            }
        )
    return {
        "value": field.value,
        "confidence": field.confidence,
        "evidence": evidence_payloads,
        "missing_evidence": field.missing_evidence or not evidence_payloads,
    }


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/listings")
def list_listings() -> Dict[str, Any]:
    fixtures = get_phase8_fixtures()
    evidence_lookup = fixtures.evidence_by_id()
    listings = []
    for listing in fixtures.listings:
        fields = {
            name: _field_payload(field, evidence_lookup)
            for name, field in listing.fields.items()
            if name in {"price", "beds", "baths", "address", "deposit", "parking"}
        }
        listings.append(
            {
                "listing_id": listing.listing_id,
                "title": listing.title,
                "neighborhood": listing.neighborhood,
                "snapshot_id": listing.snapshot_id,
                "fields": fields,
            }
        )
    return ok_response({"listings": listings})


@app.get("/api/listings/{listing_id}")
def listing_detail(listing_id: str):
    fixtures = get_phase8_fixtures()
    listing = fixtures.listings_by_id().get(listing_id)
    if listing is None:
        return JSONResponse(status_code=404, content=error_response("NOT_FOUND", "Listing not found"))
    evidence_lookup = fixtures.evidence_by_id()
    fields = {name: _field_payload(field, evidence_lookup) for name, field in listing.fields.items()}
    return ok_response(
        {
            "listing": {
                "listing_id": listing.listing_id,
                "building_id": listing.building_id,
                "neighborhood": listing.neighborhood,
                "source_id": listing.source_id,
                "title": listing.title,
                "body": listing.body,
                "snapshot_id": listing.snapshot_id,
                "fields": fields,
            }
        }
    )


@app.get("/api/listings/{listing_id}/history")
def listing_history(listing_id: str):
    fixtures = get_phase8_fixtures()
    if listing_id not in fixtures.listings_by_id():
        return JSONResponse(status_code=404, content=error_response("NOT_FOUND", "Listing not found"))
    history = fixtures.history_by_listing().get(listing_id, [])
    evidence_lookup = fixtures.evidence_by_id()
    entries = []
    for entry in history:
        evidence_payloads = []
        for evidence_id in entry.evidence_ids:
            evidence = evidence_lookup.get(evidence_id)
            if evidence:
                evidence_payloads.append(
                    {
                        "evidence_id": evidence.evidence_id,
                        "snapshot_id": evidence.snapshot_id,
                        "kind": evidence.kind,
                        "locator": evidence.locator,
                        "excerpt": evidence.excerpt,
                    }
                )
        entries.append(
            {
                "change_id": entry.change_id,
                "field_path": entry.field_path,
                "old_value": entry.old_value,
                "new_value": entry.new_value,
                "changed_at": entry.changed_at.isoformat(),
                "snapshot_id": entry.snapshot_id,
                "evidence": evidence_payloads,
            }
        )
    return ok_response({"history": entries})


@app.post("/api/compare")
def compare_listings(request: CompareRequest):
    if request.schema_version != "v1":
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "schema_version must be v1"),
        )
    if not request.listing_id_left or not request.listing_id_right:
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "Both listing IDs are required"),
        )
    if not _is_uuid(request.listing_id_left) or not _is_uuid(request.listing_id_right):
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "Listing IDs must be UUIDs"),
        )
    fixtures = get_phase8_fixtures()
    listings = fixtures.listings_by_id()
    left = listings.get(request.listing_id_left)
    right = listings.get(request.listing_id_right)
    if left is None or right is None:
        return JSONResponse(status_code=404, content=error_response("NOT_FOUND", "Listing not found"))
    if request.snapshot_id_left and request.snapshot_id_left != left.snapshot_id:
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "Left snapshot_id does not match listing"),
        )
    if request.snapshot_id_right and request.snapshot_id_right != right.snapshot_id:
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "Right snapshot_id does not match listing"),
        )

    evidence_lookup = fixtures.evidence_by_id()
    field_names = sorted(set(left.fields.keys()) | set(right.fields.keys()))
    diffs = []
    for name in field_names:
        left_field = left.fields.get(name)
        right_field = right.fields.get(name)
        diffs.append(
            {
                "field": name,
                "left": _field_payload(left_field, evidence_lookup) if left_field else None,
                "right": _field_payload(right_field, evidence_lookup) if right_field else None,
                "different": (left_field.value if left_field else None)
                != (right_field.value if right_field else None),
            }
        )
    return ok_response({"comparison": {"left_id": left.listing_id, "right_id": right.listing_id, "fields": diffs}})


@app.post("/api/near-miss")
def near_miss(request: NearMissRequest):
    if request.schema_version != "v1":
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "schema_version must be v1"),
        )
    if not request.search_spec_id:
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "search_spec_id is required"),
        )
    if request.threshold is None:
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "threshold is required"),
        )
    if request.threshold < 0 or request.threshold > 1:
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "threshold must be between 0 and 1"),
        )

    fixtures = get_phase8_fixtures()
    spec = fixtures.search_specs_by_id().get(request.search_spec_id)
    if spec is None:
        return JSONResponse(status_code=404, content=error_response("NOT_FOUND", "SearchSpec not found"))

    evidence_lookup = fixtures.evidence_by_id()
    results = []
    for listing in fixtures.listings:
        price_field = listing.fields.get("price")
        if not price_field:
            continue
        price_max = spec.hard.price_max
        if price_max is None:
            continue
        if price_field.value is None:
            continue
        if price_field.value <= price_max:
            continue
        delta = (price_field.value - price_max) / price_max
        if delta <= request.threshold:
            results.append(
                {
                    "listing_id": listing.listing_id,
                    "title": listing.title,
                    "reason": f"price_over_by_{round(delta, 3)}",
                    "price": _field_payload(price_field, evidence_lookup),
                }
            )
    return ok_response({"near_miss": results})


@app.get("/api/alerts")
def list_alerts():
    fixtures = get_phase8_fixtures()
    alerts = []
    for alert in fixtures.alerts:
        alerts.append(
            {
                "alert_id": alert.alert_id,
                "listing_id": alert.listing_id,
                "listing_change_id": alert.listing_change_id,
                "search_spec_id": alert.search_spec_id,
                "created_at": alert.created_at.isoformat(),
                "status": alert.status,
            }
        )
    return ok_response({"alerts": alerts})


@app.get("/api/evidence/{evidence_id}")
def evidence_detail(evidence_id: str):
    fixtures = get_phase8_fixtures()
    evidence = fixtures.evidence_by_id().get(evidence_id)
    if evidence is None:
        return JSONResponse(status_code=404, content=error_response("NOT_FOUND", "Evidence not found"))
    return ok_response(
        {
            "evidence": {
                "evidence_id": evidence.evidence_id,
                "snapshot_id": evidence.snapshot_id,
                "kind": evidence.kind,
                "locator": evidence.locator,
                "excerpt": evidence.excerpt,
            }
        }
    )


@app.get("/api/snapshots/{snapshot_id}")
def snapshot_detail(snapshot_id: str):
    fixtures = get_phase8_fixtures()
    snapshot = fixtures.snapshots_by_id().get(snapshot_id)
    if snapshot is None:
        return JSONResponse(status_code=404, content=error_response("NOT_FOUND", "Snapshot not found"))
    return ok_response(
        {
            "snapshot": {
                "snapshot_id": snapshot.snapshot_id,
                "url": snapshot.url,
                "content_hash": snapshot.content_hash,
                "text": snapshot.text,
                "html": snapshot.html,
            }
        }
    )


@app.get("/{path:path}", include_in_schema=False)
def spa_fallback(path: str):
    if path.startswith("api") or path.startswith("assets"):
        return JSONResponse(status_code=404, content=error_response("NOT_FOUND", "Not found"))
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
