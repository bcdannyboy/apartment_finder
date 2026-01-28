from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from services.searchspec.models import SearchSpecModel


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    fact_id: Optional[str] = None


@dataclass(frozen=True)
class StructuredField:
    value: object
    confidence: float
    evidence: List[EvidenceRef] = field(default_factory=list)


@dataclass(frozen=True)
class CommuteValue:
    anchor_id: str
    mode: str
    duration_min: float
    confidence: float


@dataclass(frozen=True)
class RankingListing:
    listing_id: str
    building_id: str
    neighborhood: str
    source_id: str
    fields: Dict[str, StructuredField] = field(default_factory=dict)
    commutes: Dict[str, CommuteValue] = field(default_factory=dict)


@dataclass(frozen=True)
class RankingScores:
    utility: float
    confidence: float
    final: float


@dataclass(frozen=True)
class RankingExplanation:
    why: List[str]
    tradeoffs: List[str]
    verify: List[str]
    flags: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RankedListing:
    listing_id: str
    rank: int
    scores: RankingScores
    explanation: RankingExplanation


@dataclass(frozen=True)
class RankingResult:
    search_spec: SearchSpecModel
    results: List[RankedListing]
    rerank_payload: List[Dict[str, object]]


@dataclass(frozen=True)
class DiversityCaps:
    per_building: int = 3
    per_neighborhood: int = 5
    per_source: int = 5


@dataclass(frozen=True)
class RankingConfig:
    hard_confidence_threshold: float = 0.8
    candidate_limit: int = 200
    diversity_caps: DiversityCaps = DiversityCaps()
    max_fields_for_rerank: int = 30
    max_evidence_per_field: int = 5
    blocked_rerank_fields: tuple[str, ...] = ("title", "body", "raw_text", "description")
    max_text_length_for_rerank: int = 200
