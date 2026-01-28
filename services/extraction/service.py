from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from services.common.evidence import EvidenceIssue, validate_evidence_ref
from services.common.enums import EvidenceKind
from services.common.facts import EvidenceRecord, FactEvidenceLink, FactRecord, FactStore
from services.extraction.determinism import deterministic_id
from services.extraction.deterministic import DeterministicExtractor
from services.extraction.models import EvidenceRef, FieldCandidate, SnapshotContent, SourceObservationRecord
from services.extraction.structured import FieldValueModel, StructuredOutputModel, StructuredOutputValidator


@dataclass(frozen=True)
class ExtractionResult:
    observation: SourceObservationRecord
    facts: List[FactRecord]
    evidence: List[EvidenceRecord]
    links: List[FactEvidenceLink]
    validation_report: Dict[str, Any]


class ExtractionRepository:
    def __init__(self) -> None:
        self._results: List[ExtractionResult] = []

    def add(self, result: ExtractionResult) -> None:
        self._results.append(result)

    def list_results(self) -> List[ExtractionResult]:
        return list(self._results)

    def list_observations(self) -> List[SourceObservationRecord]:
        return [result.observation for result in self._results]


class ExtractionService:
    def __init__(
        self,
        repository: Optional[ExtractionRepository] = None,
        *,
        extractor_version: str = "extraction/v1",
        deterministic_extractor: Optional[DeterministicExtractor] = None,
        structured_validator: Optional[StructuredOutputValidator] = None,
    ) -> None:
        self._repository = repository or ExtractionRepository()
        self._extractor_version = extractor_version
        self._deterministic = deterministic_extractor or DeterministicExtractor()
        self._validator = structured_validator or StructuredOutputValidator()

    @property
    def repository(self) -> ExtractionRepository:
        return self._repository

    def run(
        self,
        snapshot: SnapshotContent,
        *,
        structured_output: Optional[Dict[str, Any]] = None,
        repair_attempts: Optional[List[Dict[str, Any]]] = None,
        max_retries: int = 0,
        extracted_at: Optional[datetime] = None,
        extractor_version: Optional[str] = None,
    ) -> ExtractionResult:
        extracted_at = extracted_at or datetime.now(tz=timezone.utc)
        extractor_version = extractor_version or self._extractor_version

        structured_candidates: List[FieldCandidate] = []
        validation_report = {
            "schema_version": "v1",
            "status": "skipped",
            "errors": [],
            "retry_count": 0,
        }
        extracted_json: Optional[Dict[str, Any]] = None

        if structured_output is not None:
            validation = self._validator.validate(
                structured_output,
                repair_attempts=repair_attempts,
                max_retries=max_retries,
            )
            validation_report = validation.validation_report
            extracted_json = validation.extracted_json
            if validation.model is not None:
                structured_candidates = _structured_candidates(validation.model)

        deterministic_candidates = self._deterministic.extract(snapshot)
        candidates = deterministic_candidates + structured_candidates

        observation_id = deterministic_id(
            "observation",
            {
                "snapshot_id": snapshot.snapshot_id,
                "extractor_version": extractor_version,
                "extracted_json_hash": extracted_json,
            },
        )

        fact_store, evidence_issues = materialize_candidates(
            snapshot,
            observation_id,
            candidates,
            extracted_at=extracted_at,
        )

        if evidence_issues:
            validation_report = _merge_validation_report(validation_report, evidence_issues)

        observation = SourceObservationRecord(
            observation_id=observation_id,
            snapshot_id=snapshot.snapshot_id,
            source_id=snapshot.source_id,
            extracted_json=extracted_json,
            extractor_version=extractor_version,
            validation_report=validation_report,
            created_at=extracted_at,
        )

        result = ExtractionResult(
            observation=observation,
            facts=list(fact_store.facts.values()),
            evidence=list(fact_store.evidence.values()),
            links=fact_store.links,
            validation_report=validation_report,
        )
        self._repository.add(result)
        return result


def _merge_validation_report(
    base: Dict[str, Any], issues: List[EvidenceIssue]
) -> Dict[str, Any]:
    merged = dict(base)
    errors = list(merged.get("errors", []))
    for issue in issues:
        errors.append(
            {
                "code": issue.code,
                "message": issue.message,
                "path": issue.field_path,
                "severity": issue.severity,
            }
        )
    merged["errors"] = errors
    if merged.get("status") == "skipped":
        merged["status"] = "success"
    return merged


def _structured_candidates(model: StructuredOutputModel) -> List[FieldCandidate]:
    candidates: List[FieldCandidate] = []

    def add(field_path: str, field: Optional[FieldValueModel]) -> None:
        if field is None:
            return
        candidates.append(_candidate_from_field(field_path, field))

    def add_many(field_path: str, fields: Iterable[FieldValueModel]) -> None:
        for field in fields:
            candidates.append(_candidate_from_field(field_path, field))

    listing = model.listing
    add("/listing/address", listing.address)
    add_many("/listing/address", listing.address_candidates)
    add("/listing/price", listing.price)
    add_many("/listing/price", listing.price_candidates)
    add("/listing/beds", listing.beds)
    add("/listing/baths", listing.baths)
    add("/listing/availability", listing.availability)

    for unit in model.units:
        add("/units/unit_label", unit.unit_label)
        add_many("/units/unit_label", unit.unit_label_candidates)
        add("/units/price", unit.price)
        add_many("/units/price", unit.price_candidates)
        add("/units/beds", unit.beds)
        add("/units/baths", unit.baths)

    for amenity in model.amenities:
        add("/amenities/name", amenity.name)

    # Deterministic ordering
    ordered = sorted(candidates, key=lambda c: (c.field_path, str(c.value), c.extractor))
    return ordered


def _candidate_from_field(field_path: str, field: FieldValueModel) -> FieldCandidate:
    evidence_refs: List[EvidenceRef] = []
    for evidence in field.evidence:
        try:
            kind = EvidenceKind(evidence.kind)
        except ValueError:
            kind = evidence.kind  # type: ignore[assignment]
        evidence_refs.append(
            EvidenceRef(
                snapshot_id=evidence.snapshot_id,
                kind=kind,  # type: ignore[arg-type]
                locator=evidence.locator,
                excerpt=evidence.excerpt,
            )
        )
    return FieldCandidate(
        field_path=field_path,
        value=field.value,
        confidence=field.confidence,
        evidence=evidence_refs,
        extractor="structured-output",
    )


def materialize_candidates(
    snapshot: SnapshotContent,
    observation_id: str,
    candidates: List[FieldCandidate],
    *,
    extracted_at: datetime,
) -> Tuple[FactStore, List[EvidenceIssue]]:
    store = FactStore()
    issues: List[EvidenceIssue] = []

    for candidate in candidates:
        if candidate.value is None:
            continue
        if not candidate.evidence:
            issues.append(
                EvidenceIssue(
                    code="evidence_missing",
                    message="non-null field missing evidence",
                    field_path=candidate.field_path,
                )
            )
            continue
        if candidate.confidence is None:
            issues.append(
                EvidenceIssue(
                    code="confidence_missing",
                    message="non-null field missing confidence",
                    field_path=candidate.field_path,
                )
            )
            continue

        evidence_issues: List[EvidenceIssue] = []
        for evidence_ref in candidate.evidence:
            evidence_issues.extend(
                validate_evidence_ref(evidence_ref, snapshot, candidate.field_path)
            )
        if evidence_issues:
            issues.extend(evidence_issues)
            continue

        evidence_ids: List[str] = []
        for evidence_ref in candidate.evidence:
            kind_value = (
                evidence_ref.kind.value
                if isinstance(evidence_ref.kind, EvidenceKind)
                else str(evidence_ref.kind)
            )
            evidence_id = deterministic_id(
                "evidence",
                {
                    "snapshot_id": evidence_ref.snapshot_id,
                    "kind": kind_value,
                    "locator": evidence_ref.locator,
                    "excerpt": evidence_ref.excerpt,
                },
            )
            record = store.add_evidence(
                snapshot_id=evidence_ref.snapshot_id,
                kind=EvidenceKind(evidence_ref.kind),
                locator=evidence_ref.locator,
                excerpt=evidence_ref.excerpt,
                evidence_id=evidence_id,
                created_at=extracted_at,
            )
            evidence_ids.append(record.evidence_id)

        entity_type = "listing"
        if candidate.field_path.startswith("/units/"):
            entity_type = "unit"
        entity_id = deterministic_id(
            entity_type,
            {
                "snapshot_id": snapshot.snapshot_id,
                "field_path": candidate.field_path,
                "value": candidate.value,
            },
        )
        fact_id = deterministic_id(
            "fact",
            {
                "observation_id": observation_id,
                "field_path": candidate.field_path,
                "value": candidate.value,
                "extractor": candidate.extractor,
            },
        )
        store.add_fact(
            observation_id=observation_id,
            entity_type=entity_type,
            entity_id=entity_id,
            field_path=candidate.field_path,
            value_json=candidate.value,
            confidence=candidate.confidence,
            extractor=candidate.extractor,
            extracted_at=extracted_at,
            evidence_ids=evidence_ids,
            fact_id=fact_id,
        )

    return store, issues
