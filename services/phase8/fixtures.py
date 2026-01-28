from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

from services.common.hashes import sha256_text
from services.extraction.determinism import deterministic_id
from services.retrieval.models import EvidenceRef, FieldValue, ListingDocument
from services.searchspec.models import SearchSpecExplorationModel, SearchSpecHardModel, SearchSpecModel, SearchSpecSoftModel


@dataclass(frozen=True)
class FrozenSnapshotFixture:
    snapshot_id: str
    url: str
    text: str
    html: str
    content_hash: str


@dataclass(frozen=True)
class EvidenceFixture:
    evidence_id: str
    snapshot_id: str
    kind: str
    locator: Dict[str, Any]
    excerpt: Optional[str]


@dataclass(frozen=True)
class ListingFieldFixture:
    value: Any
    confidence: float
    evidence_ids: Tuple[str, ...] = ()
    missing_evidence: bool = False


@dataclass(frozen=True)
class ListingFixture:
    listing_id: str
    building_id: str
    neighborhood: str
    source_id: str
    title: str
    body: str
    snapshot_id: str
    fields: Dict[str, ListingFieldFixture]
    commutes: Dict[str, Any] = field(default_factory=dict)
    is_relevant: bool = False


@dataclass(frozen=True)
class ListingHistoryFixture:
    change_id: str
    listing_id: str
    field_path: str
    old_value: Any
    new_value: Any
    changed_at: datetime
    evidence_ids: Tuple[str, ...]
    snapshot_id: str


@dataclass(frozen=True)
class AlertFixture:
    alert_id: str
    listing_id: str
    listing_change_id: str
    search_spec_id: str
    created_at: datetime
    status: str


@dataclass(frozen=True)
class Phase8Fixtures:
    snapshots: Tuple[FrozenSnapshotFixture, ...]
    evidence: Tuple[EvidenceFixture, ...]
    listings: Tuple[ListingFixture, ...]
    history: Tuple[ListingHistoryFixture, ...]
    alerts: Tuple[AlertFixture, ...]
    search_specs: Tuple[SearchSpecModel, ...]

    def snapshots_by_id(self) -> Dict[str, FrozenSnapshotFixture]:
        return {snapshot.snapshot_id: snapshot for snapshot in self.snapshots}

    def evidence_by_id(self) -> Dict[str, EvidenceFixture]:
        return {item.evidence_id: item for item in self.evidence}

    def listings_by_id(self) -> Dict[str, ListingFixture]:
        return {listing.listing_id: listing for listing in self.listings}

    def history_by_listing(self) -> Dict[str, List[ListingHistoryFixture]]:
        grouped: Dict[str, List[ListingHistoryFixture]] = {}
        for entry in self.history:
            grouped.setdefault(entry.listing_id, []).append(entry)
        for entries in grouped.values():
            entries.sort(key=lambda item: (item.changed_at, item.change_id))
        return grouped

    def search_specs_by_id(self) -> Dict[str, SearchSpecModel]:
        return {spec.search_spec_id: spec for spec in self.search_specs}

    def listing_documents(self) -> Tuple[ListingDocument, ...]:
        docs: List[ListingDocument] = []
        for listing in sorted(self.listings, key=lambda item: item.listing_id):
            structured: Dict[str, FieldValue] = {}
            for field_name, field_value in listing.fields.items():
                evidence_refs = [EvidenceRef(evidence_id=eid) for eid in field_value.evidence_ids]
                structured[field_name] = FieldValue(
                    value=field_value.value,
                    confidence=field_value.confidence,
                    evidence=evidence_refs,
                )
            docs.append(
                ListingDocument(
                    listing_id=listing.listing_id,
                    building_id=listing.building_id,
                    neighborhood=listing.neighborhood,
                    source_id=listing.source_id,
                    title=listing.title,
                    body=listing.body,
                    structured=structured,
                    commutes=listing.commutes,
                )
            )
        return tuple(docs)

    def replace(self, **changes: Any) -> "Phase8Fixtures":
        return replace(self, **changes)


BASE_TIME = datetime(2026, 1, 28, tzinfo=timezone.utc)


def _make_id(label: str, name: str) -> str:
    return deterministic_id(label, {"name": name})


def _snapshot(snapshot_id: str, url: str, text: str) -> FrozenSnapshotFixture:
    html = f"<html><body>{text}</body></html>"
    content_hash = sha256_text(f"{html}||{text}")
    return FrozenSnapshotFixture(
        snapshot_id=snapshot_id,
        url=url,
        text=text,
        html=html,
        content_hash=content_hash,
    )


def _text_evidence(snapshot: FrozenSnapshotFixture, snippet: str, *, name: str) -> EvidenceFixture:
    start = snapshot.text.index(snippet)
    end = start + len(snippet)
    locator = {
        "snapshot_id": snapshot.snapshot_id,
        "start_char": start,
        "end_char": end,
        "text_hash": sha256_text(snippet),
        "source_format": "text",
    }
    return EvidenceFixture(
        evidence_id=_make_id("evidence", name),
        snapshot_id=snapshot.snapshot_id,
        kind="text_span",
        locator=locator,
        excerpt=snippet,
    )


def _field(value: Any, confidence: float, *evidence_ids: str, missing: bool = False) -> ListingFieldFixture:
    return ListingFieldFixture(
        value=value,
        confidence=confidence,
        evidence_ids=tuple(evidence_ids),
        missing_evidence=missing,
    )


def _search_spec(
    *,
    search_spec_id: str,
    raw_prompt: str,
    hard: SearchSpecHardModel,
) -> SearchSpecModel:
    return SearchSpecModel(
        schema_version="v1",
        search_spec_id=search_spec_id,
        created_at=BASE_TIME,
        raw_prompt=raw_prompt,
        hard=hard,
        soft=SearchSpecSoftModel(weights={"price": 0.6}),
        exploration=SearchSpecExplorationModel(pct=0.0, rules=[]),
    )


@lru_cache(maxsize=1)
def get_phase8_fixtures() -> Phase8Fixtures:
    snap_alpha = _snapshot(
        snapshot_id=_make_id("snapshot", "alpha-current"),
        url="https://example.com/listing/alpha",
        text=(
            "Listing Alpha at 123 Mission St, San Francisco. "
            "Price $3,200 per month. 2 beds. 1 bath. "
            "Deposit $1,000. Available now."
        ),
    )
    snap_bravo = _snapshot(
        snapshot_id=_make_id("snapshot", "bravo-current"),
        url="https://example.com/listing/bravo",
        text=(
            "Listing Bravo at 456 Castro St, San Francisco. "
            "Price $2,800 per month. 1 bed. 1 bath. "
            "Parking available."
        ),
    )
    snap_alpha_old = _snapshot(
        snapshot_id=_make_id("snapshot", "alpha-old"),
        url="https://example.com/listing/alpha/old",
        text="Listing Alpha price update: Price $2,800 per month.",
    )
    snap_alpha_mid = _snapshot(
        snapshot_id=_make_id("snapshot", "alpha-mid"),
        url="https://example.com/listing/alpha/mid",
        text="Listing Alpha price update: Price $3,000 per month.",
    )

    evidence_items = []
    evidence_items.extend(
        [
            _text_evidence(snap_alpha, "123 Mission St, San Francisco", name="alpha-address"),
            _text_evidence(snap_alpha, "$3,200", name="alpha-price"),
            _text_evidence(snap_alpha, "2 beds", name="alpha-beds"),
            _text_evidence(snap_alpha, "1 bath", name="alpha-baths"),
            _text_evidence(snap_alpha, "$1,000", name="alpha-deposit"),
            _text_evidence(snap_alpha, "Available now", name="alpha-availability"),
            _text_evidence(snap_bravo, "456 Castro St, San Francisco", name="bravo-address"),
            _text_evidence(snap_bravo, "$2,800", name="bravo-price"),
            _text_evidence(snap_bravo, "1 bed", name="bravo-beds"),
            _text_evidence(snap_bravo, "1 bath", name="bravo-baths"),
            _text_evidence(snap_bravo, "Parking available", name="bravo-parking"),
            _text_evidence(snap_alpha_old, "$2,800", name="alpha-old-price"),
            _text_evidence(snap_alpha_mid, "$3,000", name="alpha-mid-price"),
        ]
    )
    evidence_by_name = {item.evidence_id: item for item in evidence_items}

    alpha_id = _make_id("listing", "alpha")
    bravo_id = _make_id("listing", "bravo")

    listings = (
        ListingFixture(
            listing_id=alpha_id,
            building_id=_make_id("building", "alpha"),
            neighborhood="mission",
            source_id=_make_id("source", "alpha"),
            title="Listing Alpha",
            body="Bright two bed in Mission",
            snapshot_id=snap_alpha.snapshot_id,
            fields={
                "address": _field(
                    "123 Mission St, San Francisco",
                    0.93,
                    evidence_by_name[_make_id("evidence", "alpha-address")].evidence_id,
                ),
                "price": _field(
                    3200,
                    0.92,
                    evidence_by_name[_make_id("evidence", "alpha-price")].evidence_id,
                ),
                "beds": _field(
                    2,
                    0.88,
                    evidence_by_name[_make_id("evidence", "alpha-beds")].evidence_id,
                ),
                "baths": _field(
                    1,
                    0.86,
                    evidence_by_name[_make_id("evidence", "alpha-baths")].evidence_id,
                ),
                "deposit": _field(
                    1000,
                    0.84,
                    evidence_by_name[_make_id("evidence", "alpha-deposit")].evidence_id,
                ),
                "availability": _field(
                    "available",
                    0.8,
                    evidence_by_name[_make_id("evidence", "alpha-availability")].evidence_id,
                ),
            },
            is_relevant=True,
        ),
        ListingFixture(
            listing_id=bravo_id,
            building_id=_make_id("building", "bravo"),
            neighborhood="castro",
            source_id=_make_id("source", "bravo"),
            title="Listing Bravo",
            body="Cozy one bed near Castro",
            snapshot_id=snap_bravo.snapshot_id,
            fields={
                "address": _field(
                    "456 Castro St, San Francisco",
                    0.91,
                    evidence_by_name[_make_id("evidence", "bravo-address")].evidence_id,
                ),
                "price": _field(
                    2800,
                    0.9,
                    evidence_by_name[_make_id("evidence", "bravo-price")].evidence_id,
                ),
                "beds": _field(
                    1,
                    0.87,
                    evidence_by_name[_make_id("evidence", "bravo-beds")].evidence_id,
                ),
                "baths": _field(
                    1,
                    0.85,
                    evidence_by_name[_make_id("evidence", "bravo-baths")].evidence_id,
                ),
                "deposit": _field(500, 0.5, missing=True),
                "parking": _field(
                    True,
                    0.82,
                    evidence_by_name[_make_id("evidence", "bravo-parking")].evidence_id,
                ),
            },
            is_relevant=False,
        ),
    )

    history_entries = (
        ListingHistoryFixture(
            change_id=_make_id("change", "alpha-price-1"),
            listing_id=alpha_id,
            field_path="price",
            old_value=2800,
            new_value=3000,
            changed_at=BASE_TIME - timedelta(days=18),
            evidence_ids=(
                evidence_by_name[_make_id("evidence", "alpha-old-price")].evidence_id,
                evidence_by_name[_make_id("evidence", "alpha-mid-price")].evidence_id,
            ),
            snapshot_id=snap_alpha_mid.snapshot_id,
        ),
        ListingHistoryFixture(
            change_id=_make_id("change", "alpha-price-2"),
            listing_id=alpha_id,
            field_path="price",
            old_value=3000,
            new_value=3200,
            changed_at=BASE_TIME - timedelta(days=8),
            evidence_ids=(
                evidence_by_name[_make_id("evidence", "alpha-mid-price")].evidence_id,
                evidence_by_name[_make_id("evidence", "alpha-price")].evidence_id,
            ),
            snapshot_id=snap_alpha.snapshot_id,
        ),
    )

    specs = (
        _search_spec(
            search_spec_id=_make_id("searchspec", "eval"),
            raw_prompt="two bed under 3500 mission",
            hard=SearchSpecHardModel(
                price_max=3500,
                beds_min=2,
                baths_min=1,
                neighborhoods_include=["mission"],
            ),
        ),
        _search_spec(
            search_spec_id=_make_id("searchspec", "near-miss"),
            raw_prompt="two bed under 3000 mission",
            hard=SearchSpecHardModel(
                price_max=3000,
                beds_min=2,
                baths_min=1,
                neighborhoods_include=["mission"],
            ),
        ),
    )

    alerts = (
        AlertFixture(
            alert_id=_make_id("alert", "alpha-1"),
            listing_id=alpha_id,
            listing_change_id=history_entries[1].change_id,
            search_spec_id=specs[0].search_spec_id,
            created_at=BASE_TIME - timedelta(days=7),
            status="pending",
        ),
        AlertFixture(
            alert_id=_make_id("alert", "bravo-1"),
            listing_id=bravo_id,
            listing_change_id=history_entries[0].change_id,
            search_spec_id=specs[0].search_spec_id,
            created_at=BASE_TIME - timedelta(days=6),
            status="succeeded",
        ),
    )

    return Phase8Fixtures(
        snapshots=(snap_alpha, snap_bravo, snap_alpha_old, snap_alpha_mid),
        evidence=tuple(evidence_items),
        listings=listings,
        history=history_entries,
        alerts=alerts,
        search_specs=specs,
    )
