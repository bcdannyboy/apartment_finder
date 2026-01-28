from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.common.enums import EvidenceKind
from services.common.facts import FactStore
from services.dedupe.determinism import stable_hash
from services.dedupe.models import CanonicalField, Cluster, ListingInput
from services.dedupe.service import CanonicalizationService, DedupeConfig, DedupeService, ListingChangeStore, ThresholdBands
from services.extraction.determinism import deterministic_id
from services.normalization.service import NormalizationService


FIXED_TIME = datetime(2026, 1, 28, tzinfo=timezone.utc)


def _pair_key(left_id: str, right_id: str) -> str:
    return f"{left_id}|{right_id}" if left_id <= right_id else f"{right_id}|{left_id}"


def _make_listing(
    *,
    listing_id: str,
    source_id: str,
    observation_id: str,
    observed_at: datetime,
    address: str | None = None,
    unit_label: str | None = None,
    price: str | None = None,
    confidence: float = 0.8,
) -> ListingInput:
    store = FactStore()
    snapshot_id = f"snap-{observation_id}"

    def add_fact(field_path: str, value: str | None, conf: float) -> None:
        if value is None:
            return
        field_key = field_path.strip("/").replace("/", "-")
        evidence_id = f"ev-{observation_id}-{field_key}"
        store.add_evidence(
            snapshot_id=snapshot_id,
            kind=EvidenceKind.text_span,
            locator={"start_char": 0, "end_char": 1},
            evidence_id=evidence_id,
        )
        store.add_fact(
            observation_id=observation_id,
            entity_type="listing",
            entity_id=listing_id,
            field_path=field_path,
            value_json=value,
            confidence=conf,
            extractor="test",
            extracted_at=observed_at,
            evidence_ids=[evidence_id],
            fact_id=f"fact-{observation_id}-{field_key}",
        )

    add_fact("/listing/address", address, confidence)
    add_fact("/units/unit_label", unit_label, confidence)
    add_fact("/listing/price", price, confidence)

    normalizer = NormalizationService()
    normalized = normalizer.normalize(list(store.facts.values()), store.links)
    return ListingInput(
        listing_id=listing_id,
        observation_id=observation_id,
        source_id=source_id,
        observed_at=observed_at,
        facts=list(store.facts.values()),
        normalized_facts=normalized,
        evidence_links=store.links,
    )


def _fact_id(listing: ListingInput, field_path: str) -> str:
    for fact in listing.facts:
        if fact.field_path == field_path:
            return fact.fact_id
    raise AssertionError(f"Missing fact for {field_path}")


def _fact_value(listing: ListingInput, field_path: str) -> str:
    for fact in listing.facts:
        if fact.field_path == field_path:
            return fact.value_json
    raise AssertionError(f"Missing fact for {field_path}")


def _cluster_for(listing_ids: list[str]) -> Cluster:
    members = sorted(listing_ids)
    cluster_id = deterministic_id("cluster", {"members": members})
    return Cluster(cluster_id=cluster_id, members=tuple(members))


def _default_config(score_overrides: dict[str, float] | None = None) -> DedupeConfig:
    return DedupeConfig(
        thresholds=ThresholdBands(auto_merge=0.85, review=0.6),
        score_overrides=score_overrides,
    )


def test_t4_01_blocking_reproducible():
    listings = [
        _make_listing(
            listing_id="list-1",
            source_id="source-a",
            observation_id="obs-1",
            observed_at=FIXED_TIME,
            address="123 Main St",
            unit_label="1A",
            price="$2000",
        ),
        _make_listing(
            listing_id="list-2",
            source_id="source-b",
            observation_id="obs-2",
            observed_at=FIXED_TIME,
            address="123 Main St",
            unit_label="1A",
            price="$2000",
        ),
    ]
    service = DedupeService(_default_config())
    first = service.block(listings)
    second = service.block(listings)
    assert first.blocking_keys == second.blocking_keys
    assert first.candidate_pairs == second.candidate_pairs
    assert first.pair_counts_by_key == second.pair_counts_by_key


def test_t4_02_blocking_recall_duplicates():
    listings = [
        _make_listing(
            listing_id="list-1",
            source_id="source-a",
            observation_id="obs-1",
            observed_at=FIXED_TIME,
            address="500 Market St",
            unit_label="2B",
            price="$2500",
        ),
        _make_listing(
            listing_id="list-2",
            source_id="source-b",
            observation_id="obs-2",
            observed_at=FIXED_TIME,
            address="500 Market St",
            unit_label="2B",
            price="$2500",
        ),
        _make_listing(
            listing_id="list-3",
            source_id="source-c",
            observation_id="obs-3",
            observed_at=FIXED_TIME,
            address="999 Broadway",
            unit_label="9C",
            price="$3200",
        ),
    ]
    service = DedupeService(_default_config())
    blocking = service.block(listings)
    pairs = {(pair.left_id, pair.right_id) for pair in blocking.candidate_pairs}
    assert ("list-1", "list-2") in pairs


def test_t4_03_pair_scoring_reproducible():
    listings = [
        _make_listing(
            listing_id="list-1",
            source_id="source-a",
            observation_id="obs-1",
            observed_at=FIXED_TIME,
            address="100 Pine St",
            unit_label="3C",
            price="$2100",
        ),
        _make_listing(
            listing_id="list-2",
            source_id="source-b",
            observation_id="obs-2",
            observed_at=FIXED_TIME,
            address="100 Pine St",
            unit_label="3C",
            price="$2100",
        ),
    ]
    service = DedupeService(_default_config())
    blocking = service.block(listings)
    first = service.score(listings, blocking.candidate_pairs)
    second = service.score(listings, blocking.candidate_pairs)
    assert [(pair.left_id, pair.right_id, pair.score) for pair in first] == [
        (pair.left_id, pair.right_id, pair.score) for pair in second
    ]


def test_t4_04_threshold_band_enforcement():
    service = DedupeService(_default_config())
    assert service.band_for_score(0.85) == "auto_merge"
    assert service.band_for_score(0.84) == "review"
    assert service.band_for_score(0.6) == "review"
    assert service.band_for_score(0.59) == "auto_separate"


def test_t4_05_review_band_non_destructive():
    listings = [
        _make_listing(
            listing_id="list-1",
            source_id="source-a",
            observation_id="obs-1",
            observed_at=FIXED_TIME,
            address="42 Mission St",
            unit_label="7D",
            price="$3000",
        ),
        _make_listing(
            listing_id="list-2",
            source_id="source-b",
            observation_id="obs-2",
            observed_at=FIXED_TIME,
            address="42 Mission St",
            unit_label="7D",
            price="$3000",
        ),
    ]
    overrides = {_pair_key("list-1", "list-2"): 0.7}
    service = DedupeService(_default_config(score_overrides=overrides))
    result = service.run(listings)
    assert len(result.review_queue) == 1
    assert all(len(cluster.members) == 1 for cluster in result.clusters)


def test_t4_06_canonical_merge_trust_priority():
    older = FIXED_TIME - timedelta(days=5)
    newer = FIXED_TIME
    listing_high_trust = _make_listing(
        listing_id="list-1",
        source_id="source-high",
        observation_id="obs-1",
        observed_at=older,
        address="77 King St",
        unit_label="10A",
        price="$2000",
        confidence=0.7,
    )
    listing_low_trust = _make_listing(
        listing_id="list-2",
        source_id="source-low",
        observation_id="obs-2",
        observed_at=newer,
        address="77 King St",
        unit_label="10A",
        price="$2100",
        confidence=0.8,
    )
    cluster = _cluster_for(["list-1", "list-2"])
    canonicalizer = CanonicalizationService({"source-high": 0.9, "source-low": 0.1})
    result = canonicalizer.canonicalize(
        cluster=cluster,
        listing_inputs=[listing_high_trust, listing_low_trust],
    )
    price_field = result.canonical_fields["/listing/price"]
    assert price_field.fact_id == _fact_id(listing_high_trust, "/listing/price")
    assert price_field.reason == "trust"


def test_t4_07_canonical_merge_recency_tiebreak():
    older = FIXED_TIME - timedelta(days=3)
    newer = FIXED_TIME
    listing_older = _make_listing(
        listing_id="list-1",
        source_id="source-a",
        observation_id="obs-1",
        observed_at=older,
        address="1 Lombard St",
        unit_label="2A",
        price="$1900",
    )
    listing_newer = _make_listing(
        listing_id="list-2",
        source_id="source-b",
        observation_id="obs-2",
        observed_at=newer,
        address="1 Lombard St",
        unit_label="2A",
        price="$2000",
    )
    cluster = _cluster_for(["list-1", "list-2"])
    canonicalizer = CanonicalizationService({"source-a": 0.5, "source-b": 0.5})
    result = canonicalizer.canonicalize(
        cluster=cluster,
        listing_inputs=[listing_older, listing_newer],
    )
    price_field = result.canonical_fields["/listing/price"]
    assert price_field.fact_id == _fact_id(listing_newer, "/listing/price")
    assert price_field.reason == "recency"


def test_t4_07_canonical_merge_confidence_tiebreak():
    listing_low_conf = _make_listing(
        listing_id="list-1",
        source_id="source-a",
        observation_id="obs-1",
        observed_at=FIXED_TIME,
        address="9 Pine St",
        unit_label="1B",
        price="$2300",
        confidence=0.6,
    )
    listing_high_conf = _make_listing(
        listing_id="list-2",
        source_id="source-b",
        observation_id="obs-2",
        observed_at=FIXED_TIME,
        address="9 Pine St",
        unit_label="1B",
        price="$2400",
        confidence=0.9,
    )
    cluster = _cluster_for(["list-1", "list-2"])
    canonicalizer = CanonicalizationService({"source-a": 0.5, "source-b": 0.5})
    result = canonicalizer.canonicalize(
        cluster=cluster,
        listing_inputs=[listing_low_conf, listing_high_conf],
    )
    price_field = result.canonical_fields["/listing/price"]
    assert price_field.fact_id == _fact_id(listing_high_conf, "/listing/price")
    assert price_field.reason == "confidence"


def test_t4_08_conflicting_facts_retained():
    listing_one = _make_listing(
        listing_id="list-1",
        source_id="source-a",
        observation_id="obs-1",
        observed_at=FIXED_TIME,
        address="5 Howard St",
        unit_label="8A",
        price="$2100",
    )
    listing_two = _make_listing(
        listing_id="list-2",
        source_id="source-b",
        observation_id="obs-2",
        observed_at=FIXED_TIME,
        address="5 Howard St",
        unit_label="8A",
        price="$2200",
    )
    all_fact_ids = {fact.fact_id for listing in (listing_one, listing_two) for fact in listing.facts}
    cluster = _cluster_for(["list-1", "list-2"])
    canonicalizer = CanonicalizationService({"source-a": 0.5, "source-b": 0.5})
    result = canonicalizer.canonicalize(
        cluster=cluster,
        listing_inputs=[listing_one, listing_two],
    )
    price_fact_ids = {fact.fact_id for listing in (listing_one, listing_two) for fact in listing.facts}
    assert all_fact_ids == price_fact_ids
    assert result.canonical_fields["/listing/price"].fact_id in all_fact_ids


def test_t4_09_listing_change_idempotent():
    older = FIXED_TIME - timedelta(days=2)
    newer = FIXED_TIME
    listing_old = _make_listing(
        listing_id="list-1",
        source_id="source-a",
        observation_id="obs-1",
        observed_at=older,
        address="200 Main St",
        unit_label="4C",
        price="$2000",
    )
    listing_new = _make_listing(
        listing_id="list-2",
        source_id="source-b",
        observation_id="obs-2",
        observed_at=newer,
        address="200 Main St",
        unit_label="4C",
        price="$2100",
    )
    cluster = _cluster_for(["list-1", "list-2"])
    previous = {
        "/listing/address": CanonicalField(
            field_path="/listing/address",
            fact_id=_fact_id(listing_old, "/listing/address"),
            value_json=_fact_value(listing_old, "/listing/address"),
            reason="only",
            trust_score=0.5,
            observed_at=older,
            confidence=0.8,
        ),
        "/listing/price": CanonicalField(
            field_path="/listing/price",
            fact_id=_fact_id(listing_old, "/listing/price"),
            value_json=_fact_value(listing_old, "/listing/price"),
            reason="only",
            trust_score=0.5,
            observed_at=older,
            confidence=0.8,
        )
    }
    canonicalizer = CanonicalizationService({"source-a": 0.5, "source-b": 0.5})
    store = ListingChangeStore()
    first = canonicalizer.canonicalize(
        cluster=cluster,
        listing_inputs=[listing_old, listing_new],
        previous_canonical=previous,
        change_store=store,
    )
    assert len(first.listing_changes) == 1
    change = first.listing_changes[0]
    assert change.old_value_json != change.new_value_json
    second = canonicalizer.canonicalize(
        cluster=cluster,
        listing_inputs=[listing_old, listing_new],
        previous_canonical=previous,
        change_store=store,
    )
    assert not second.listing_changes
    assert len(store.list()) == 1


def test_t4_10_no_deletion_of_facts():
    listings = [
        _make_listing(
            listing_id="list-1",
            source_id="source-a",
            observation_id="obs-1",
            observed_at=FIXED_TIME,
            address="8 Market St",
            unit_label="5A",
            price="$2600",
        ),
        _make_listing(
            listing_id="list-2",
            source_id="source-b",
            observation_id="obs-2",
            observed_at=FIXED_TIME,
            address="8 Market St",
            unit_label="5A",
            price="$2650",
        ),
    ]
    fact_ids_before = {fact.fact_id for listing in listings for fact in listing.facts}
    service = DedupeService(_default_config())
    dedupe = service.run(listings)
    canonicalizer = CanonicalizationService({"source-a": 0.5, "source-b": 0.5})
    for cluster in dedupe.clusters:
        canonicalizer.canonicalize(cluster=cluster, listing_inputs=listings)
    fact_ids_after = {fact.fact_id for listing in listings for fact in listing.facts}
    assert fact_ids_before == fact_ids_after


def test_t4_11_end_to_end_determinism():
    listings = [
        _make_listing(
            listing_id="list-1",
            source_id="source-a",
            observation_id="obs-1",
            observed_at=FIXED_TIME,
            address="55 Pine St",
            unit_label="1A",
            price="$2100",
        ),
        _make_listing(
            listing_id="list-2",
            source_id="source-b",
            observation_id="obs-2",
            observed_at=FIXED_TIME,
            address="55 Pine St",
            unit_label="1A",
            price="$2100",
        ),
        _make_listing(
            listing_id="list-3",
            source_id="source-c",
            observation_id="obs-3",
            observed_at=FIXED_TIME,
            address="400 Elm St",
            unit_label="9F",
            price="$3300",
        ),
    ]
    trust = {"source-a": 0.6, "source-b": 0.6, "source-c": 0.4}
    service = DedupeService(_default_config())

    def run_pipeline():
        dedupe = service.run(listings)
        canonicalizer = CanonicalizationService(trust)
        canonical_results = [
            canonicalizer.canonicalize(cluster=cluster, listing_inputs=listings)
            for cluster in dedupe.clusters
        ]
        payload = {
            "clusters": [(cluster.cluster_id, cluster.members) for cluster in dedupe.clusters],
            "scores": [(pair.left_id, pair.right_id, pair.score) for pair in dedupe.scored_pairs],
            "canonical": {
                result.cluster_id: {
                    field_path: field.fact_id for field_path, field in result.canonical_fields.items()
                }
                for result in canonical_results
            },
            "changes": [
                (change.change_id, change.field_path, change.old_value_json, change.new_value_json)
                for result in canonical_results
                for change in result.listing_changes
            ],
        }
        return stable_hash(payload)

    first = run_pipeline()
    second = run_pipeline()
    assert first == second
