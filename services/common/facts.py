from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from services.common.enums import EvidenceKind


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    snapshot_id: str
    kind: EvidenceKind
    locator: Dict[str, Any]
    excerpt: Optional[str]
    created_at: datetime


@dataclass(frozen=True)
class FactRecord:
    fact_id: str
    observation_id: str
    entity_type: str
    entity_id: str
    field_path: str
    value_json: Any
    confidence: Optional[float]
    extractor: str
    extracted_at: datetime
    is_canonical: bool


@dataclass(frozen=True)
class FactEvidenceLink:
    fact_id: str
    evidence_id: str
    rank: int


class EvidenceValidationError(ValueError):
    pass


class FactValidationError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _validate_text_span(locator: Dict[str, Any]) -> None:
    try:
        start = int(locator["start_char"])
        end = int(locator["end_char"])
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceValidationError("text_span requires start_char and end_char") from exc
    if start < 0 or end < 0 or start >= end:
        raise EvidenceValidationError("text_span locator must have start_char < end_char")


def _validate_image_region(locator: Dict[str, Any]) -> None:
    for key in ("width", "height", "x", "y"):
        if key not in locator:
            raise EvidenceValidationError("image_region requires x, y, width, height")
    width = int(locator["width"])
    height = int(locator["height"])
    if width <= 0 or height <= 0:
        raise EvidenceValidationError("image_region requires positive width and height")


class FactStore:
    def __init__(self) -> None:
        self._evidence: Dict[str, EvidenceRecord] = {}
        self._facts: Dict[str, FactRecord] = {}
        self._links: List[FactEvidenceLink] = []

    @property
    def evidence(self) -> Dict[str, EvidenceRecord]:
        return dict(self._evidence)

    @property
    def facts(self) -> Dict[str, FactRecord]:
        return dict(self._facts)

    @property
    def links(self) -> List[FactEvidenceLink]:
        return list(self._links)

    def add_evidence(
        self,
        *,
        snapshot_id: str,
        kind: EvidenceKind,
        locator: Dict[str, Any],
        excerpt: Optional[str] = None,
        evidence_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> EvidenceRecord:
        if kind == EvidenceKind.text_span:
            _validate_text_span(locator)
        elif kind == EvidenceKind.image_region:
            _validate_image_region(locator)
        else:
            raise EvidenceValidationError("Unsupported evidence kind")

        record = EvidenceRecord(
            evidence_id=evidence_id or str(uuid4()),
            snapshot_id=snapshot_id,
            kind=kind,
            locator=locator,
            excerpt=excerpt,
            created_at=created_at or _now(),
        )
        self._evidence[record.evidence_id] = record
        return record

    def add_fact(
        self,
        *,
        observation_id: str,
        entity_type: str,
        entity_id: str,
        field_path: str,
        value_json: Any,
        confidence: Optional[float],
        extractor: str,
        extracted_at: Optional[datetime] = None,
        is_canonical: bool = False,
        evidence_ids: Optional[List[str]] = None,
        fact_id: Optional[str] = None,
    ) -> FactRecord:
        evidence_ids = evidence_ids or []
        if value_json is not None:
            if not evidence_ids:
                raise FactValidationError("Evidence required for non-null fields")
            if confidence is None:
                raise FactValidationError("Confidence required for non-null fields")
        for evidence_id in evidence_ids:
            if evidence_id not in self._evidence:
                raise FactValidationError("Evidence id does not exist")

        record = FactRecord(
            fact_id=fact_id or str(uuid4()),
            observation_id=observation_id,
            entity_type=entity_type,
            entity_id=entity_id,
            field_path=field_path,
            value_json=value_json,
            confidence=confidence,
            extractor=extractor,
            extracted_at=extracted_at or _now(),
            is_canonical=is_canonical,
        )
        self._facts[record.fact_id] = record
        if evidence_ids:
            for rank, evidence_id in enumerate(evidence_ids, start=1):
                self._links.append(
                    FactEvidenceLink(
                        fact_id=record.fact_id,
                        evidence_id=evidence_id,
                        rank=rank,
                    )
                )
        return record
