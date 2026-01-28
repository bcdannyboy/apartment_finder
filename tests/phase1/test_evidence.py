import pytest

from services.common.enums import EvidenceKind
from services.common.facts import FactStore, FactValidationError


def test_fact_requires_evidence_for_non_null_fields():
    store = FactStore()
    with pytest.raises(FactValidationError):
        store.add_fact(
            observation_id="obs-1",
            entity_type="listing",
            entity_id="entity-1",
            field_path="/price",
            value_json=2500,
            confidence=0.9,
            extractor="unit-test",
            evidence_ids=[],
        )


def test_fact_and_evidence_link_created():
    store = FactStore()
    evidence = store.add_evidence(
        snapshot_id="snap-1",
        kind=EvidenceKind.text_span,
        locator={"start_char": 0, "end_char": 10},
        excerpt="$2,500",
    )
    fact = store.add_fact(
        observation_id="obs-1",
        entity_type="listing",
        entity_id="entity-1",
        field_path="/price",
        value_json=2500,
        confidence=0.9,
        extractor="unit-test",
        evidence_ids=[evidence.evidence_id],
    )
    assert fact.fact_id in store.facts
    assert store.links[0].fact_id == fact.fact_id
    assert store.links[0].evidence_id == evidence.evidence_id
    assert store.links[0].rank == 1
