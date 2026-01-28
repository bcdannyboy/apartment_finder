from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Tuple

from services.common.facts import FactEvidenceLink, FactRecord
from services.normalization.models import NormalizedFact


@dataclass(frozen=True)
class ListingInput:
    listing_id: str
    observation_id: str
    source_id: str
    observed_at: datetime
    facts: List[FactRecord]
    normalized_facts: List[NormalizedFact]
    evidence_links: List[FactEvidenceLink]


@dataclass(frozen=True)
class PairCandidate:
    left_id: str
    right_id: str
    blocking_keys: Tuple[str, ...]


@dataclass(frozen=True)
class BlockingResult:
    blocking_keys: Tuple[str, ...]
    block_membership: Dict[str, Tuple[str, ...]]
    candidate_pairs: Tuple[PairCandidate, ...]
    pair_counts_by_key: Dict[str, int]


@dataclass(frozen=True)
class ScoredPair:
    left_id: str
    right_id: str
    features: Dict[str, float]
    score: float
    model_version: str


@dataclass(frozen=True)
class PairDecision:
    left_id: str
    right_id: str
    score: float
    band: str


@dataclass(frozen=True)
class ReviewQueueItem:
    left_id: str
    right_id: str
    score: float


@dataclass(frozen=True)
class Cluster:
    cluster_id: str
    members: Tuple[str, ...]


@dataclass(frozen=True)
class DedupeResult:
    blocking: BlockingResult
    scored_pairs: Tuple[ScoredPair, ...]
    decisions: Tuple[PairDecision, ...]
    clusters: Tuple[Cluster, ...]
    review_queue: Tuple[ReviewQueueItem, ...]
    evidence_hashes: Dict[str, str]


@dataclass(frozen=True)
class CanonicalField:
    field_path: str
    fact_id: str
    value_json: Any
    reason: str
    trust_score: float
    observed_at: datetime
    confidence: float


@dataclass(frozen=True)
class ListingChange:
    change_id: str
    listing_id: str
    field_path: str
    old_value_json: Any
    new_value_json: Any
    changed_at: datetime


@dataclass(frozen=True)
class CanonicalizationResult:
    cluster_id: str
    listing_ids: Tuple[str, ...]
    canonical_fields: Dict[str, CanonicalField]
    listing_changes: List[ListingChange]
