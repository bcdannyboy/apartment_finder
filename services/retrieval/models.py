from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    fact_id: Optional[str] = None


@dataclass(frozen=True)
class FieldValue:
    value: object
    confidence: float
    evidence: List[EvidenceRef] = field(default_factory=list)


@dataclass(frozen=True)
class CommuteInfo:
    anchor_id: str
    mode: str
    duration_min: float
    confidence: float


@dataclass(frozen=True)
class ListingDocument:
    listing_id: str
    building_id: str
    neighborhood: str
    source_id: str
    title: str
    body: str
    structured: Dict[str, FieldValue] = field(default_factory=dict)
    commutes: Dict[str, CommuteInfo] = field(default_factory=dict)
    embedding: Optional[List[float]] = None


@dataclass(frozen=True)
class RetrievalQuery:
    keywords: List[str]
    vector: Optional[List[float]] = None
    external_query: Optional[str] = None


@dataclass(frozen=True)
class RetrievalCandidate:
    listing_id: str
    fts_score: float = 0.0
    vector_score: float = 0.0
    external_score: float = 0.0
    combined_score: float = 0.0


@dataclass(frozen=True)
class RetrievalAuditEvent:
    layer: str
    details: Dict[str, object]


@dataclass(frozen=True)
class RetrievalResult:
    candidates: List[RetrievalCandidate]
    audit_events: List[RetrievalAuditEvent]
