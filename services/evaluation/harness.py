from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

from services.common.hashes import sha256_text
from services.extraction.determinism import stable_json
from services.phase8.fixtures import Phase8Fixtures
from services.ranking.service import RankingService
from services.retrieval.repository import ListingRepository
from services.retrieval.service import RetrievalService


class SnapshotMutationError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvaluationReport:
    snapshot_ids: Tuple[str, ...]
    metrics: Dict[str, float]
    outputs: Dict[str, Any]
    output_hash: str
    audit_log: Dict[str, Any]


def _snapshot_hash(snapshot) -> str:
    html = snapshot.html or ""
    text = snapshot.text or ""
    return sha256_text(f"{html}||{text}")


def _validate_snapshots(fixtures: Phase8Fixtures) -> None:
    for snapshot in fixtures.snapshots:
        computed = _snapshot_hash(snapshot)
        if computed != snapshot.content_hash:
            raise SnapshotMutationError("Frozen snapshot content_hash mismatch")


def _build_repo(fixtures: Phase8Fixtures) -> ListingRepository:
    repo = ListingRepository()
    for listing in fixtures.listing_documents():
        repo.add(listing)
    return repo


def _precision_recall_f1(predicted: Iterable[str], actual: Iterable[str]) -> Tuple[float, float, float]:
    predicted_set = set(predicted)
    actual_set = set(actual)
    true_positive = len(predicted_set & actual_set)
    precision = true_positive / len(predicted_set) if predicted_set else 0.0
    recall = true_positive / len(actual_set) if actual_set else 0.0
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def run_evaluation(
    fixtures: Phase8Fixtures,
    *,
    search_spec_id: str,
    limit: int = 10,
    threshold: float = 0.0,
) -> EvaluationReport:
    _validate_snapshots(fixtures)

    specs = fixtures.search_specs_by_id()
    spec = specs.get(search_spec_id)
    if spec is None:
        raise ValueError("SearchSpec not found")

    repo = _build_repo(fixtures)
    retrieval = RetrievalService(repo)
    ranking = RankingService(listings=repo, retrieval=retrieval)
    result = ranking.rank(spec, limit=limit)

    ordered_results = sorted(result.results, key=lambda item: (item.rank, item.listing_id))
    predicted = [item.listing_id for item in ordered_results if item.scores.final >= threshold]

    actual = [listing.listing_id for listing in fixtures.listings if listing.is_relevant]

    precision, recall, f1 = _precision_recall_f1(predicted, actual)

    total_fields = 0
    fields_with_evidence = 0
    missing_evidence = 0
    listing_lookup = fixtures.listings_by_id()
    for listing_id in predicted:
        listing = listing_lookup.get(listing_id)
        if not listing:
            continue
        for field in listing.fields.values():
            if field.value is None:
                continue
            total_fields += 1
            if field.evidence_ids:
                fields_with_evidence += 1
            if field.missing_evidence or not field.evidence_ids:
                missing_evidence += 1

    evidence_coverage = fields_with_evidence / total_fields if total_fields else 1.0
    missing_evidence_rate = missing_evidence / total_fields if total_fields else 0.0

    metrics = {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "evidence_coverage": evidence_coverage,
        "missing_evidence_rate": missing_evidence_rate,
    }

    outputs = {
        "predicted_listing_ids": sorted(predicted),
        "ground_truth_ids": sorted(actual),
        "ranking": [
            {"listing_id": item.listing_id, "rank": item.rank, "score": item.scores.final}
            for item in ordered_results
        ],
    }

    audit_log = {
        "snapshot_ids": tuple(sorted(snapshot.snapshot_id for snapshot in fixtures.snapshots)),
        "search_spec_id": spec.search_spec_id,
        "api_endpoints": [],
        "outputs": outputs,
    }

    output_hash = sha256_text(stable_json({"metrics": metrics, "outputs": outputs}))

    return EvaluationReport(
        snapshot_ids=tuple(sorted(snapshot.snapshot_id for snapshot in fixtures.snapshots)),
        metrics=metrics,
        outputs=outputs,
        output_hash=output_hash,
        audit_log=audit_log,
    )
