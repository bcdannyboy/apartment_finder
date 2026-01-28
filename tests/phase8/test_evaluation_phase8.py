from __future__ import annotations

from dataclasses import replace
import math

import pytest

from services.evaluation.harness import SnapshotMutationError, run_evaluation
from services.phase8.fixtures import get_phase8_fixtures


def test_evaluation_deterministic_repeatability():
    fixtures = get_phase8_fixtures()
    spec_id = fixtures.search_specs[0].search_spec_id
    report1 = run_evaluation(fixtures, search_spec_id=spec_id, limit=5)
    report2 = run_evaluation(fixtures, search_spec_id=spec_id, limit=5)
    assert report1.output_hash == report2.output_hash
    assert report1.metrics == report2.metrics


def test_evaluation_order_independence():
    fixtures = get_phase8_fixtures()
    spec_id = fixtures.search_specs[0].search_spec_id
    reordered = fixtures.replace(
        snapshots=tuple(reversed(fixtures.snapshots)),
        listings=tuple(reversed(fixtures.listings)),
    )
    report1 = run_evaluation(fixtures, search_spec_id=spec_id, limit=5)
    report2 = run_evaluation(reordered, search_spec_id=spec_id, limit=5)
    assert report1.output_hash == report2.output_hash


def test_evaluation_snapshot_immutability_enforced():
    fixtures = get_phase8_fixtures()
    mutated_snapshot = replace(fixtures.snapshots[0], text=fixtures.snapshots[0].text + " mutation")
    mutated = fixtures.replace(snapshots=(mutated_snapshot,) + fixtures.snapshots[1:])
    with pytest.raises(SnapshotMutationError):
        run_evaluation(mutated, search_spec_id=fixtures.search_specs[0].search_spec_id)


def test_evaluation_metric_sanity_and_consistency():
    fixtures = get_phase8_fixtures()
    report = run_evaluation(fixtures, search_spec_id=fixtures.search_specs[0].search_spec_id)
    metrics = report.metrics

    for value in metrics.values():
        assert math.isfinite(value)
        assert 0.0 <= value <= 1.0

    precision = metrics["precision"]
    recall = metrics["recall"]
    if precision + recall == 0:
        expected_f1 = 0.0
    else:
        expected_f1 = 2 * precision * recall / (precision + recall)
    assert metrics["f1"] == expected_f1

    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0


def test_evaluation_missing_data_handling():
    fixtures = get_phase8_fixtures()
    report = run_evaluation(fixtures, search_spec_id=fixtures.search_specs[0].search_spec_id)
    assert report.metrics["missing_evidence_rate"] >= 0.0
    assert report.metrics["evidence_coverage"] <= 1.0
