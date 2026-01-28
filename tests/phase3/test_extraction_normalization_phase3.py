from __future__ import annotations

from datetime import datetime, timezone

from services.common.evidence import resolve_text_span, validate_evidence_ref
from services.common.enums import EvidenceKind
from services.extraction.deterministic import DeterministicExtractor
from services.extraction.models import ImageMeta, SnapshotContent
from services.extraction.service import ExtractionRepository, ExtractionService, materialize_candidates
from services.extraction.structured import StructuredOutputValidator
from services.normalization.service import NormalizationService


FIXED_TIME = datetime(2026, 1, 28, tzinfo=timezone.utc)


def _snapshot(
    *,
    snapshot_id: str,
    source_id: str = "source-1",
    html: str | None = None,
    text: str | None = None,
    markdown: str | None = None,
    images: dict[str, ImageMeta] | None = None,
) -> SnapshotContent:
    return SnapshotContent(
        snapshot_id=snapshot_id,
        source_id=source_id,
        html=html,
        text=text,
        markdown=markdown,
        images=images or {},
    )


def _text_evidence(snapshot: SnapshotContent, snippet: str, *, source_format: str = "text"):
    content = snapshot.text if source_format == "text" else snapshot.html
    assert content is not None
    start = content.index(snippet)
    end = start + len(snippet)
    return {
        "snapshot_id": snapshot.snapshot_id,
        "kind": "text_span",
        "locator": {
            "snapshot_id": snapshot.snapshot_id,
            "start_char": start,
            "end_char": end,
            "source_format": source_format,
        },
        "excerpt": snippet,
    }


def _jsonld_html(price: str = "1950") -> str:
    return (
        "<html><head><script type=\"application/ld+json\">"
        "{"
        "\"@context\":\"https://schema.org\","
        "\"@type\":\"Apartment\","
        "\"address\":\"123 1/2 Main St, San Francisco, CA\","
        f"\"numberOfBedrooms\":2,\"numberOfBathroomsTotal\":1.5,"
        f"\"offers\":{{\"price\":\"{price}\",\"availability\":\"https://schema.org/InStock\"}}"
        "}"
        "</script></head><body>Rent $1,950/mo · 2 beds · 1.5 bath · 123 1/2 Main St, San Francisco</body></html>"
    )


def _fix_p3_001() -> SnapshotContent:
    html = _jsonld_html()
    text = "Rent $1,950/mo · 2 beds · 1.5 bath · 123 1/2 Main St, San Francisco"
    return _snapshot(snapshot_id="snap-p3-001", html=html, text=text)


def _fix_p3_002() -> SnapshotContent:
    text = "Now leasing $2,400 per month. 3 beds, 2 baths at 456 Market St, San Francisco"
    return _snapshot(snapshot_id="snap-p3-002", text=text, html="<html><body>No jsonld here</body></html>")


def _fix_p3_003() -> SnapshotContent:
    text = "Tour 111 First St, San Francisco or 222 Second St, San Francisco today."
    return _snapshot(snapshot_id="snap-p3-003", text=text)


def _fix_p3_004() -> SnapshotContent:
    text = "Unit A: $2,000 1 bed. Unit B: $2,500 2 beds."
    return _snapshot(snapshot_id="snap-p3-004", text=text)


def _fix_p3_005() -> SnapshotContent:
    html = _jsonld_html(price="2000")
    text = "Special price $2,100 per month."
    return _snapshot(snapshot_id="snap-p3-005", html=html, text=text)


def _fix_p3_006() -> SnapshotContent:
    images = {"floorplan-1": ImageMeta(image_ref="floorplan-1", width=800, height=600)}
    return _snapshot(snapshot_id="snap-p3-006", images=images)


def _fix_p3_008() -> SnapshotContent:
    text = "Rent $2000 Rent $2000"
    return _snapshot(snapshot_id="snap-p3-008", text=text)


def _fix_p3_009() -> SnapshotContent:
    return _fix_p3_001()


def test_p3_ex_001_jsonld_extraction_deterministic():
    snapshot = _fix_p3_001()
    extractor = DeterministicExtractor()
    first = extractor.extract(snapshot)
    second = extractor.extract(snapshot)
    assert [c.field_path for c in first] == [c.field_path for c in second]
    assert [c.value for c in first] == [c.value for c in second]
    assert [c.evidence[0].locator for c in first] == [c.evidence[0].locator for c in second]


def test_p3_ex_002_regex_extraction_deterministic():
    snapshot = _fix_p3_002()
    extractor = DeterministicExtractor()
    first = extractor.extract(snapshot)
    second = extractor.extract(snapshot)
    assert [c.value for c in first] == [c.value for c in second]
    assert [c.evidence[0].locator for c in first] == [c.evidence[0].locator for c in second]


def test_p3_ex_003_deterministic_parser_ambiguity():
    snapshot = _fix_p3_003()
    extractor = DeterministicExtractor()
    candidates = extractor.extract(snapshot)
    addresses = [c.value for c in candidates if c.field_path == "/listing/address"]
    assert any(value.startswith("111 First St") for value in addresses)
    assert any(value.startswith("222 Second St") for value in addresses)
    assert len(addresses) == 2


def test_p3_ex_004_conflicts_preserved():
    snapshot = _fix_p3_005()
    extractor = DeterministicExtractor()
    candidates = extractor.extract(snapshot)
    prices = [c.value for c in candidates if c.field_path == "/listing/price"]
    assert "2000" in prices
    assert any("2,100" in price or "2100" in price for price in prices)
    assert len(prices) >= 2


def test_p3_so_001_valid_structured_outputs_pass():
    snapshot = _fix_p3_001()
    output = {
        "schema_version": "v1",
        "listing": {
            "address": {
                "value": "123 1/2 Main St, San Francisco",
                "confidence": 0.9,
                "evidence": [_text_evidence(snapshot, "123 1/2 Main St, San Francisco")],
            },
            "price": {
                "value": "$1,950/mo",
                "confidence": 0.9,
                "evidence": [_text_evidence(snapshot, "$1,950/mo")],
            },
            "beds": {
                "value": 2,
                "confidence": 0.8,
                "evidence": [_text_evidence(snapshot, "2 beds")],
            },
            "baths": {
                "value": 1.5,
                "confidence": 0.8,
                "evidence": [_text_evidence(snapshot, "1.5 bath")],
            },
        },
        "units": [],
        "amenities": [],
    }
    validator = StructuredOutputValidator()
    validation = validator.validate(output)
    assert validation.validation_report["status"] == "success"
    service = ExtractionService()
    result = service.run(snapshot, structured_output=output, extracted_at=FIXED_TIME)
    assert result.validation_report["status"] == "success"
    assert any(fact.field_path == "/listing/price" for fact in result.facts)


def test_p3_so_002_type_mismatch_schema_failure():
    snapshot = _fix_p3_001()
    output = {
        "schema_version": "v1",
        "listing": {
            "beds": {
                "value": "two",
                "confidence": 0.5,
                "evidence": [_text_evidence(snapshot, "2 beds")],
            }
        },
        "units": [],
        "amenities": [],
    }
    validator = StructuredOutputValidator()
    validation = validator.validate(output)
    assert validation.validation_report["status"] == "failure"
    assert any("/listing/beds" in error["path"] for error in validation.validation_report["errors"])


def test_p3_so_003_missing_required_keys_schema_failure():
    output = {"schema_version": "v1"}
    validator = StructuredOutputValidator()
    validation = validator.validate(output)
    assert validation.validation_report["status"] == "failure"
    assert any("/listing" in error["path"] for error in validation.validation_report["errors"])


def test_p3_so_004_bounded_repair_retry_recorded():
    snapshot = _fix_p3_001()
    invalid = {"schema_version": "v1", "listing": {"beds": {"value": "two"}}, "units": [], "amenities": []}
    valid = {
        "schema_version": "v1",
        "listing": {
            "beds": {
                "value": 2,
                "confidence": 0.7,
                "evidence": [_text_evidence(snapshot, "2 beds")],
            }
        },
        "units": [],
        "amenities": [],
    }
    validator = StructuredOutputValidator()
    validation = validator.validate(invalid, repair_attempts=[valid], max_retries=1)
    assert validation.validation_report["retry_count"] >= 1
    assert validation.validation_report["status"] == "success"


def test_p3_ev_001_missing_evidence_invalidates_field():
    snapshot = _fix_p3_002()
    output = {
        "schema_version": "v1",
        "listing": {
            "price": {"value": "$2,400", "confidence": 0.8, "evidence": []}
        },
        "units": [],
        "amenities": [],
    }
    service = ExtractionService()
    result = service.run(snapshot, structured_output=output, extracted_at=FIXED_TIME)
    assert any(error["code"] == "evidence_missing" for error in result.validation_report["errors"])
    assert not any(
        fact.field_path == "/listing/price" and fact.extractor == "structured-output"
        for fact in result.facts
    )


def test_p3_ev_002_deterministic_requires_evidence():
    snapshot = _fix_p3_002()
    candidates = []
    # Candidate without evidence should be dropped.
    from services.extraction.models import FieldCandidate, EvidenceRef

    candidates.append(
        FieldCandidate(
            field_path="/listing/price",
            value="$2400",
            confidence=0.9,
            evidence=[],
            extractor="deterministic-regex",
        )
    )
    store, issues = materialize_candidates(
        snapshot,
        observation_id="obs-1",
        candidates=candidates,
        extracted_at=FIXED_TIME,
    )
    assert issues
    assert not store.facts


def test_p3_ev_003_nested_arrays_require_evidence():
    snapshot = _fix_p3_004()
    output = {
        "schema_version": "v1",
        "listing": {},
        "units": [
            {
                "unit_label": {
                    "value": "Unit A",
                    "confidence": 0.8,
                    "evidence": [_text_evidence(snapshot, "Unit A")],
                },
                "price": {
                    "value": "$2,000",
                    "confidence": 0.8,
                    "evidence": [_text_evidence(snapshot, "$2,000")],
                },
                "beds": {
                    "value": 1,
                    "confidence": 0.8,
                    "evidence": [_text_evidence(snapshot, "1 bed")],
                },
            },
            {
                "unit_label": {
                    "value": "Unit B",
                    "confidence": 0.8,
                    "evidence": [_text_evidence(snapshot, "Unit B")],
                },
                "price": {
                    "value": "$2,500",
                    "confidence": 0.8,
                    "evidence": [_text_evidence(snapshot, "$2,500")],
                },
                "beds": {
                    "value": 2,
                    "confidence": 0.8,
                    "evidence": [_text_evidence(snapshot, "2 beds")],
                },
            },
        ],
        "amenities": [
            {
                "name": {
                    "value": "Laundry",
                    "confidence": 0.6,
                    "evidence": [_text_evidence(snapshot, "Unit")],
                }
            }
        ],
    }
    service = ExtractionService()
    result = service.run(snapshot, structured_output=output, extracted_at=FIXED_TIME)
    assert any(fact.field_path == "/units/unit_label" for fact in result.facts)
    assert any(fact.field_path == "/amenities/name" for fact in result.facts)


def test_p3_amb_001_structured_address_candidates():
    snapshot = _fix_p3_003()
    output = {
        "schema_version": "v1",
        "listing": {
            "address_candidates": [
                {
                    "value": "111 First St, San Francisco",
                    "confidence": 0.7,
                    "evidence": [_text_evidence(snapshot, "111 First St, San Francisco")],
                },
                {
                    "value": "222 Second St, San Francisco",
                    "confidence": 0.7,
                    "evidence": [_text_evidence(snapshot, "222 Second St, San Francisco")],
                },
            ]
        },
        "units": [],
        "amenities": [],
    }
    service = ExtractionService()
    result = service.run(snapshot, structured_output=output, extracted_at=FIXED_TIME)
    addresses = [fact.value_json for fact in result.facts if fact.field_path == "/listing/address"]
    assert any(address == "111 First St, San Francisco" for address in addresses)
    assert any(address == "222 Second St, San Francisco" for address in addresses)


def test_p3_amb_002_multiple_rents_preserved_in_normalization():
    snapshot = _fix_p3_004()
    extractor = DeterministicExtractor()
    candidates = extractor.extract(snapshot)
    store, _issues = materialize_candidates(
        snapshot,
        observation_id="obs-2",
        candidates=candidates,
        extracted_at=FIXED_TIME,
    )
    normalizer = NormalizationService()
    normalized = normalizer.normalize(list(store.facts.values()), store.links)
    prices = [item.normalized_value for item in normalized if item.field_path.endswith("/price")]
    assert len(prices) >= 2


def test_p3_amb_003_ambiguous_unit_identifiers_preserved():
    snapshot = _fix_p3_004()
    output = {
        "schema_version": "v1",
        "listing": {},
        "units": [
            {
                "unit_label": {
                    "value": "Unit A",
                    "confidence": 0.8,
                    "evidence": [_text_evidence(snapshot, "Unit A")],
                }
            },
            {
                "unit_label": {
                    "value": "Unit B",
                    "confidence": 0.8,
                    "evidence": [_text_evidence(snapshot, "Unit B")],
                }
            },
        ],
        "amenities": [],
    }
    service = ExtractionService()
    result = service.run(snapshot, structured_output=output, extracted_at=FIXED_TIME)
    normalizer = NormalizationService()
    normalized = normalizer.normalize(result.facts, result.links)
    labels = [item.raw_value for item in normalized if item.field_path == "/units/unit_label"]
    assert "Unit A" in labels
    assert "Unit B" in labels


def test_p3_val_001_validation_report_on_failure():
    snapshot = _fix_p3_002()
    output = {"schema_version": "v1", "listing": {"beds": {"value": "two"}}, "units": [], "amenities": []}
    service = ExtractionService()
    result = service.run(snapshot, structured_output=output, extracted_at=FIXED_TIME)
    assert result.observation.validation_report["status"] == "failure"
    assert result.observation.extracted_json is None


def test_p3_val_002_validation_report_has_details():
    snapshot = _fix_p3_002()
    output = {"schema_version": "v1", "listing": {"beds": {"value": "two"}}, "units": [], "amenities": []}
    service = ExtractionService()
    result = service.run(snapshot, structured_output=output, extracted_at=FIXED_TIME)
    report = result.validation_report
    assert report["schema_version"] == "v1"
    assert report["status"] == "failure"
    assert any("path" in error for error in report["errors"])
    assert "raw_output_hash" in report


def test_p3_val_003_failed_validation_emits_no_facts():
    snapshot = _snapshot(snapshot_id="snap-p3-007")
    output = {"schema_version": "v1", "listing": {"beds": {"value": "two"}}, "units": [], "amenities": []}
    service = ExtractionService()
    result = service.run(snapshot, structured_output=output, extracted_at=FIXED_TIME)
    assert not result.facts


def test_p3_norm_001_raw_and_normalized_values_persist():
    snapshot = _fix_p3_001()
    extractor = DeterministicExtractor()
    candidates = extractor.extract(snapshot)
    store, _issues = materialize_candidates(
        snapshot,
        observation_id="obs-3",
        candidates=candidates,
        extracted_at=FIXED_TIME,
    )
    normalizer = NormalizationService()
    normalized = normalizer.normalize(list(store.facts.values()), store.links)
    raw_values = [item.raw_value for item in normalized if item.field_path.endswith("/price")]
    normalized_values = [item.normalized_value for item in normalized if item.field_path.endswith("/price")]
    assert any("1,950" in str(value) for value in raw_values)
    assert any(value == 1950.0 for value in normalized_values)


def test_p3_norm_002_fractional_address_preserved():
    snapshot = _fix_p3_001()
    extractor = DeterministicExtractor()
    candidates = extractor.extract(snapshot)
    store, _issues = materialize_candidates(
        snapshot,
        observation_id="obs-4",
        candidates=candidates,
        extracted_at=FIXED_TIME,
    )
    normalizer = NormalizationService()
    normalized = normalizer.normalize(list(store.facts.values()), store.links)
    addresses = [item.normalized_value for item in normalized if item.field_path.endswith("/address")]
    assert any("1/2" in str(addr) for addr in addresses)


def test_p3_norm_003_bed_bath_normalization_preserves_evidence():
    snapshot = _fix_p3_001()
    extractor = DeterministicExtractor()
    candidates = extractor.extract(snapshot)
    store, _issues = materialize_candidates(
        snapshot,
        observation_id="obs-5",
        candidates=candidates,
        extracted_at=FIXED_TIME,
    )
    normalizer = NormalizationService()
    normalized = normalizer.normalize(list(store.facts.values()), store.links)
    baths = [item for item in normalized if item.field_path.endswith("/baths")]
    assert baths
    assert any(item.normalized_value == 1.5 for item in baths)
    assert all(item.evidence_ids for item in baths)


def test_p3_norm_004_conflicting_values_not_overwritten():
    snapshot = _fix_p3_005()
    extractor = DeterministicExtractor()
    candidates = extractor.extract(snapshot)
    store, _issues = materialize_candidates(
        snapshot,
        observation_id="obs-6",
        candidates=candidates,
        extracted_at=FIXED_TIME,
    )
    normalizer = NormalizationService()
    normalized = normalizer.normalize(list(store.facts.values()), store.links)
    prices = [item.normalized_value for item in normalized if item.field_path.endswith("/price")]
    assert len(set(prices)) >= 2


def test_p3_loc_001_text_span_resolves_and_excerpt_matches():
    snapshot = _fix_p3_001()
    evidence = _text_evidence(snapshot, "$1,950/mo")
    issue_list = validate_evidence_ref(
        _to_evidence_ref(evidence),
        snapshot,
        "/listing/price",
    )
    assert not issue_list
    span = resolve_text_span(snapshot, evidence["locator"])
    assert span == "$1,950/mo"


def test_p3_loc_002_repeated_substrings_correct_occurrence():
    snapshot = _fix_p3_008()
    text = snapshot.text
    assert text is not None
    second = text.index("$2000", text.index("$2000") + 1)
    evidence = {
        "snapshot_id": snapshot.snapshot_id,
        "kind": "text_span",
        "locator": {
            "snapshot_id": snapshot.snapshot_id,
            "start_char": second,
            "end_char": second + len("$2000"),
            "source_format": "text",
        },
        "excerpt": "$2000",
    }
    issues = validate_evidence_ref(_to_evidence_ref(evidence), snapshot, "/listing/price")
    assert not issues
    assert resolve_text_span(snapshot, evidence["locator"]) == "$2000"


def test_p3_loc_003_image_region_within_bounds():
    snapshot = _fix_p3_006()
    evidence = {
        "snapshot_id": snapshot.snapshot_id,
        "kind": "image_region",
        "locator": {
            "snapshot_id": snapshot.snapshot_id,
            "image_ref": "floorplan-1",
            "x": 10,
            "y": 10,
            "width": 200,
            "height": 150,
        },
        "excerpt": None,
    }
    issues = validate_evidence_ref(_to_evidence_ref(evidence), snapshot, "/listing/price")
    assert not issues


def test_p3_loc_004_snapshot_id_mismatch():
    snapshot = _fix_p3_001()
    evidence = _text_evidence(snapshot, "$1,950/mo")
    evidence["snapshot_id"] = "snap-other"
    issues = validate_evidence_ref(_to_evidence_ref(evidence), snapshot, "/listing/price")
    assert any(issue.code == "snapshot_id_mismatch" for issue in issues)


def test_p3_det_001_deterministic_parsers_stable():
    snapshot = _fix_p3_009()
    extractor = DeterministicExtractor()
    first = extractor.extract(snapshot)
    second = extractor.extract(snapshot)
    assert [(c.field_path, c.value) for c in first] == [
        (c.field_path, c.value) for c in second
    ]


def test_p3_det_002_structured_outputs_replay_stable():
    snapshot = _fix_p3_001()
    output = {
        "schema_version": "v1",
        "listing": {
            "price": {
                "value": "$1,950/mo",
                "confidence": 0.9,
                "evidence": [_text_evidence(snapshot, "$1,950/mo")],
            }
        },
        "units": [],
        "amenities": [],
    }
    service = ExtractionService()
    first = service.run(snapshot, structured_output=output, extracted_at=FIXED_TIME)
    second = service.run(snapshot, structured_output=output, extracted_at=FIXED_TIME)
    assert [fact.fact_id for fact in first.facts] == [fact.fact_id for fact in second.facts]
    assert [ev.evidence_id for ev in first.evidence] == [
        ev.evidence_id for ev in second.evidence
    ]


def test_p3_det_003_normalization_stable():
    snapshot = _fix_p3_001()
    extractor = DeterministicExtractor()
    candidates = extractor.extract(snapshot)
    store, _issues = materialize_candidates(
        snapshot,
        observation_id="obs-7",
        candidates=candidates,
        extracted_at=FIXED_TIME,
    )
    normalizer = NormalizationService()
    first = normalizer.normalize(list(store.facts.values()), store.links)
    second = normalizer.normalize(list(store.facts.values()), store.links)
    assert [item.normalized_fact_id for item in first] == [
        item.normalized_fact_id for item in second
    ]


def test_p3_det_004_version_changes_do_not_overwrite():
    snapshot = _fix_p3_001()
    repo = ExtractionRepository()
    service = ExtractionService(repository=repo, extractor_version="extraction/v1")
    service.run(snapshot, extracted_at=FIXED_TIME)
    service.run(snapshot, extracted_at=FIXED_TIME, extractor_version="extraction/v2")
    observations = repo.list_observations()
    versions = [obs.extractor_version for obs in observations]
    assert "extraction/v1" in versions
    assert "extraction/v2" in versions


def _to_evidence_ref(payload: dict):
    from services.extraction.models import EvidenceRef

    return EvidenceRef(
        snapshot_id=payload["snapshot_id"],
        kind=EvidenceKind(payload["kind"]),
        locator=payload["locator"],
        excerpt=payload.get("excerpt"),
    )
