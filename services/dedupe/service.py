from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from services.dedupe.determinism import stable_hash
from services.dedupe.models import (
    BlockingResult,
    CanonicalField,
    CanonicalizationResult,
    Cluster,
    DedupeResult,
    ListingChange,
    ListingInput,
    PairCandidate,
    PairDecision,
    ReviewQueueItem,
    ScoredPair,
)
from services.extraction.determinism import deterministic_id


@dataclass(frozen=True)
class ThresholdBands:
    auto_merge: float
    review: float


@dataclass(frozen=True)
class DedupeConfig:
    thresholds: ThresholdBands
    model_version: str = "dedupe-score/v1"
    blocking_version: str = "dedupe-blocking/v1"
    price_tolerance: float = 100.0
    score_weights: Dict[str, float] = None  # type: ignore[assignment]
    score_overrides: Optional[Dict[str, float]] = None

    def __post_init__(self) -> None:
        if self.score_weights is None:
            object.__setattr__(
                self,
                "score_weights",
                {
                    "address_match": 0.6,
                    "unit_match": 0.3,
                    "price_match": 0.1,
                },
            )


class ListingChangeStore:
    def __init__(self) -> None:
        self._changes: Dict[str, ListingChange] = {}

    def record(self, change: ListingChange) -> bool:
        if change.change_id in self._changes:
            return False
        self._changes[change.change_id] = change
        return True

    def list(self) -> List[ListingChange]:
        return list(self._changes.values())


class _UnionFind:
    def __init__(self, items: Iterable[str]) -> None:
        self._parent = {item: item for item in items}

    def find(self, item: str) -> str:
        parent = self._parent[item]
        if parent != item:
            self._parent[item] = self.find(parent)
        return self._parent[item]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            if left_root < right_root:
                self._parent[right_root] = left_root
            else:
                self._parent[left_root] = right_root

    def groups(self) -> Dict[str, List[str]]:
        grouped: Dict[str, List[str]] = {}
        for item in self._parent:
            root = self.find(item)
            grouped.setdefault(root, []).append(item)
        for members in grouped.values():
            members.sort()
        return grouped


class DedupeService:
    def __init__(self, config: DedupeConfig) -> None:
        self._config = config
        self._validate_thresholds()

    def _validate_thresholds(self) -> None:
        auto_merge = self._config.thresholds.auto_merge
        review = self._config.thresholds.review
        if not (0.0 <= review <= auto_merge <= 1.0):
            raise ValueError("Threshold bands must satisfy 0 <= review <= auto_merge <= 1")

    def _normalized_values(self, listing: ListingInput, field_path: str) -> List[str]:
        values = [
            str(item.normalized_value).strip()
            for item in listing.normalized_facts
            if item.field_path == field_path and item.normalized_value is not None
        ]
        return values

    def _normalize_key(self, value: str) -> str:
        return " ".join(value.strip().lower().split())

    def _blocking_keys(self, listing: ListingInput) -> List[str]:
        addresses = [self._normalize_key(val) for val in self._normalized_values(listing, "/listing/address")]
        units = [self._normalize_key(val) for val in self._normalized_values(listing, "/units/unit_label")]
        keys: List[str] = []
        for address in addresses:
            keys.append(f"addr:{address}")
            for unit in units:
                keys.append(f"addr_unit:{address}|{unit}")
        return sorted(set(keys))

    def _pair_key(self, left_id: str, right_id: str) -> str:
        if left_id <= right_id:
            return f"{left_id}|{right_id}"
        return f"{right_id}|{left_id}"

    def block(self, listings: Sequence[ListingInput]) -> BlockingResult:
        block_membership: Dict[str, List[str]] = {}
        for listing in listings:
            keys = self._blocking_keys(listing)
            for key in keys:
                block_membership.setdefault(key, []).append(listing.listing_id)

        for key in block_membership:
            block_membership[key].sort()

        pair_map: Dict[Tuple[str, str], List[str]] = {}
        pair_counts_by_key: Dict[str, int] = {}
        for key in sorted(block_membership):
            listing_ids = block_membership[key]
            count = 0
            for i in range(len(listing_ids)):
                for j in range(i + 1, len(listing_ids)):
                    left_id = listing_ids[i]
                    right_id = listing_ids[j]
                    pair_map.setdefault((left_id, right_id), []).append(key)
                    count += 1
            pair_counts_by_key[key] = count

        candidate_pairs = []
        for (left_id, right_id), keys in sorted(pair_map.items()):
            candidate_pairs.append(
                PairCandidate(
                    left_id=left_id,
                    right_id=right_id,
                    blocking_keys=tuple(sorted(keys)),
                )
            )

        return BlockingResult(
            blocking_keys=tuple(sorted(block_membership)),
            block_membership={key: tuple(value) for key, value in sorted(block_membership.items())},
            candidate_pairs=tuple(candidate_pairs),
            pair_counts_by_key=pair_counts_by_key,
        )

    def _feature_value_match(self, left_values: List[str], right_values: List[str]) -> Optional[float]:
        if not left_values or not right_values:
            return None
        return 1.0 if set(left_values) & set(right_values) else 0.0

    def _price_match(self, left_values: List[str], right_values: List[str]) -> Optional[float]:
        if not left_values or not right_values:
            return None
        left_nums = []
        right_nums = []
        for value in left_values:
            try:
                left_nums.append(float(value))
            except ValueError:
                continue
        for value in right_values:
            try:
                right_nums.append(float(value))
            except ValueError:
                continue
        if not left_nums or not right_nums:
            return None
        min_diff = min(abs(l - r) for l in left_nums for r in right_nums)
        return 1.0 if min_diff <= self._config.price_tolerance else 0.0

    def _score_features(self, features: Dict[str, Optional[float]]) -> float:
        total_weight = 0.0
        weighted = 0.0
        for name, value in features.items():
            if value is None:
                continue
            weight = float(self._config.score_weights.get(name, 0.0))
            total_weight += weight
            weighted += weight * value
        if total_weight == 0:
            return 0.0
        return weighted / total_weight

    def score(self, listings: Sequence[ListingInput], pairs: Sequence[PairCandidate]) -> Tuple[ScoredPair, ...]:
        listing_map = {listing.listing_id: listing for listing in listings}
        scored_pairs: List[ScoredPair] = []
        for pair in pairs:
            left = listing_map[pair.left_id]
            right = listing_map[pair.right_id]
            address_left = [self._normalize_key(val) for val in self._normalized_values(left, "/listing/address")]
            address_right = [self._normalize_key(val) for val in self._normalized_values(right, "/listing/address")]
            unit_left = [self._normalize_key(val) for val in self._normalized_values(left, "/units/unit_label")]
            unit_right = [self._normalize_key(val) for val in self._normalized_values(right, "/units/unit_label")]
            price_left = [str(val) for val in self._normalized_values(left, "/listing/price")]
            price_right = [str(val) for val in self._normalized_values(right, "/listing/price")]

            features: Dict[str, Optional[float]] = {
                "address_match": self._feature_value_match(address_left, address_right),
                "unit_match": self._feature_value_match(unit_left, unit_right),
                "price_match": self._price_match(price_left, price_right),
            }
            score = self._score_features(features)

            pair_key = self._pair_key(pair.left_id, pair.right_id)
            if self._config.score_overrides and pair_key in self._config.score_overrides:
                score = self._config.score_overrides[pair_key]

            scored_pairs.append(
                ScoredPair(
                    left_id=pair.left_id,
                    right_id=pair.right_id,
                    features={name: value or 0.0 for name, value in features.items()},
                    score=score,
                    model_version=self._config.model_version,
                )
            )
        scored_pairs.sort(key=lambda item: (item.left_id, item.right_id))
        return tuple(scored_pairs)

    def band_for_score(self, score: float) -> str:
        if score >= self._config.thresholds.auto_merge:
            return "auto_merge"
        if score >= self._config.thresholds.review:
            return "review"
        return "auto_separate"

    def decide(self, scored_pairs: Sequence[ScoredPair]) -> Tuple[PairDecision, ...]:
        decisions = []
        for pair in scored_pairs:
            decisions.append(
                PairDecision(
                    left_id=pair.left_id,
                    right_id=pair.right_id,
                    score=pair.score,
                    band=self.band_for_score(pair.score),
                )
            )
        decisions.sort(key=lambda item: (item.left_id, item.right_id))
        return tuple(decisions)

    def cluster(self, listing_ids: Sequence[str], decisions: Sequence[PairDecision]) -> Tuple[Cluster, ...]:
        union_find = _UnionFind(listing_ids)
        for decision in decisions:
            if decision.band == "auto_merge":
                union_find.union(decision.left_id, decision.right_id)

        groups = union_find.groups()
        clusters: List[Cluster] = []
        for members in sorted(groups.values()):
            cluster_id = deterministic_id("cluster", {"members": members})
            clusters.append(Cluster(cluster_id=cluster_id, members=tuple(members)))
        clusters.sort(key=lambda item: item.cluster_id)
        return tuple(clusters)

    def run(self, listings: Sequence[ListingInput]) -> DedupeResult:
        blocking = self.block(listings)
        scored_pairs = self.score(listings, blocking.candidate_pairs)
        decisions = self.decide(scored_pairs)
        clusters = self.cluster([listing.listing_id for listing in listings], decisions)
        review_queue = tuple(
            ReviewQueueItem(left_id=d.left_id, right_id=d.right_id, score=d.score)
            for d in decisions
            if d.band == "review"
        )

        evidence_hashes = {
            "blocking_keys": stable_hash(blocking.blocking_keys),
            "candidate_pairs": stable_hash(
                [(pair.left_id, pair.right_id, pair.blocking_keys) for pair in blocking.candidate_pairs]
            ),
            "scores": stable_hash([(pair.left_id, pair.right_id, pair.score) for pair in scored_pairs]),
            "clusters": stable_hash([(cluster.cluster_id, cluster.members) for cluster in clusters]),
        }

        return DedupeResult(
            blocking=blocking,
            scored_pairs=scored_pairs,
            decisions=decisions,
            clusters=clusters,
            review_queue=review_queue,
            evidence_hashes=evidence_hashes,
        )


class CanonicalizationService:
    def __init__(self, source_trust: Dict[str, float]) -> None:
        self._source_trust = source_trust

    def _evidence_map(self, listing_inputs: Sequence[ListingInput]) -> Dict[str, List[str]]:
        mapping: Dict[str, List[str]] = {}
        for listing in listing_inputs:
            for link in listing.evidence_links:
                mapping.setdefault(link.fact_id, []).append(link.evidence_id)
        return mapping

    def _ranking_tuple(self, trust: float, observed_at: datetime, confidence: float, fact_id: str) -> Tuple:
        return (trust, observed_at, confidence, fact_id)

    def _winner_reason(self, winner: Tuple, runner_up: Optional[Tuple]) -> str:
        if runner_up is None:
            return "only"
        if winner[0] != runner_up[0]:
            return "trust"
        if winner[1] != runner_up[1]:
            return "recency"
        if winner[2] != runner_up[2]:
            return "confidence"
        return "tie_breaker"

    def canonicalize(
        self,
        *,
        cluster: Cluster,
        listing_inputs: Sequence[ListingInput],
        previous_canonical: Optional[Dict[str, CanonicalField]] = None,
        change_store: Optional[ListingChangeStore] = None,
    ) -> CanonicalizationResult:
        previous_canonical = previous_canonical or {}
        change_store = change_store or ListingChangeStore()

        listing_map = {listing.listing_id: listing for listing in listing_inputs}
        evidence_map = self._evidence_map(listing_inputs)
        facts_by_field: Dict[str, List[Tuple]] = {}

        for listing_id in cluster.members:
            listing = listing_map[listing_id]
            for fact in listing.facts:
                if not fact.field_path.startswith("/listing/"):
                    continue
                if fact.value_json is None:
                    continue
                if fact.confidence is None:
                    continue
                if not evidence_map.get(fact.fact_id):
                    continue
                trust = self._source_trust.get(listing.source_id, 0.0)
                observed_at = fact.extracted_at
                confidence = float(fact.confidence)
                facts_by_field.setdefault(fact.field_path, []).append(
                    (trust, observed_at, confidence, fact.fact_id, fact.value_json)
                )

        canonical_fields: Dict[str, CanonicalField] = {}
        for field_path, candidates in facts_by_field.items():
            ordered = sorted(candidates, key=lambda item: self._ranking_tuple(item[0], item[1], item[2], item[3]))
            winner = ordered[-1]
            runner_up = ordered[-2] if len(ordered) > 1 else None
            reason = self._winner_reason(winner, runner_up)
            canonical_fields[field_path] = CanonicalField(
                field_path=field_path,
                fact_id=winner[3],
                value_json=winner[4],
                reason=reason,
                trust_score=winner[0],
                observed_at=winner[1],
                confidence=winner[2],
            )

        listing_changes: List[ListingChange] = []
        all_fields = sorted(set(previous_canonical) | set(canonical_fields))
        for field_path in all_fields:
            old_field = previous_canonical.get(field_path)
            new_field = canonical_fields.get(field_path)
            old_value = old_field.value_json if old_field else None
            new_value = new_field.value_json if new_field else None
            if old_value == new_value:
                continue
            changed_at = new_field.observed_at if new_field else old_field.observed_at  # type: ignore[union-attr]
            change_id = deterministic_id(
                "listing_change",
                {
                    "listing_id": cluster.cluster_id,
                    "field_path": field_path,
                    "old_value": old_value,
                    "new_value": new_value,
                },
            )
            change = ListingChange(
                change_id=change_id,
                listing_id=cluster.cluster_id,
                field_path=field_path,
                old_value_json=old_value,
                new_value_json=new_value,
                changed_at=changed_at,
            )
            if change_store.record(change):
                listing_changes.append(change)

        listing_changes.sort(key=lambda item: (item.field_path, str(item.old_value_json), str(item.new_value_json)))
        return CanonicalizationResult(
            cluster_id=cluster.cluster_id,
            listing_ids=cluster.members,
            canonical_fields=canonical_fields,
            listing_changes=listing_changes,
        )
