from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from services.ranking.models import (
    CommuteValue,
    DiversityCaps,
    EvidenceRef,
    RankedListing,
    RankingConfig,
    RankingExplanation,
    RankingListing,
    RankingResult,
    RankingScores,
    StructuredField,
)
from services.retrieval.models import ListingDocument, RetrievalQuery
from services.retrieval.repository import ListingRepository
from services.retrieval.service import RetrievalService
from services.searchspec.models import SearchSpecModel


@dataclass(frozen=True)
class RankingObservabilityEvent:
    event_type: str
    details: Dict[str, object]


class RankingObservability:
    def __init__(self) -> None:
        self._events: List[RankingObservabilityEvent] = []

    def record(self, event_type: str, **details: object) -> None:
        self._events.append(RankingObservabilityEvent(event_type=event_type, details=details))

    def events(self) -> List[RankingObservabilityEvent]:
        return list(self._events)


class RankingService:
    def __init__(
        self,
        *,
        listings: ListingRepository,
        retrieval: RetrievalService,
        config: Optional[RankingConfig] = None,
        observability: Optional[RankingObservability] = None,
    ) -> None:
        self._listings = listings
        self._retrieval = retrieval
        self._config = config or RankingConfig()
        self._observability = observability or RankingObservability()

    @property
    def observability(self) -> RankingObservability:
        return self._observability

    def rank(self, search_spec: SearchSpecModel, *, limit: int = 50) -> RankingResult:
        query = self._build_query(search_spec)
        retrieval_result = self._retrieval.retrieve(query, limit=self._config.candidate_limit)
        self._observability.record(
            "retrieval",
            candidate_count=len(retrieval_result.candidates),
            layers=[event.layer for event in retrieval_result.audit_events],
        )
        listing_docs = self._hydrate_listings(retrieval_result.candidates)
        filtered, flags = self._apply_hard_filters(listing_docs, search_spec)
        scored = [self._score(listing, search_spec, flags.get(listing.listing_id, [])) for listing in filtered]
        scored.sort(key=lambda item: (-item.scores.final, item.listing_id))
        rerank_payload = self._build_rerank_payload(filtered)
        diversified = self._apply_diversity_caps(scored, self._config.diversity_caps)
        ranked = []
        for index, result in enumerate(diversified[:limit], start=1):
            ranked.append(
                RankedListing(
                    listing_id=result.listing_id,
                    rank=index,
                    scores=result.scores,
                    explanation=result.explanation,
                )
            )
        return RankingResult(search_spec=search_spec, results=ranked, rerank_payload=rerank_payload)

    def _build_query(self, search_spec: SearchSpecModel) -> RetrievalQuery:
        raw = search_spec.raw_prompt or ""
        keywords = [token for token in raw.lower().split() if token]
        return RetrievalQuery(keywords=keywords)

    def _hydrate_listings(self, candidates) -> List[RankingListing]:
        listings: List[RankingListing] = []
        for candidate in candidates:
            doc = self._listings.get(candidate.listing_id)
            if doc is None:
                continue
            listings.append(_to_ranking_listing(doc))
        return listings

    def _apply_hard_filters(
        self,
        listings: List[RankingListing],
        search_spec: SearchSpecModel,
    ) -> Tuple[List[RankingListing], Dict[str, List[str]]]:
        flags: Dict[str, List[str]] = {}
        kept: List[RankingListing] = []
        for listing in listings:
            passes, listing_flags = self._evaluate_listing(listing, search_spec)
            if passes:
                kept.append(listing)
            if listing_flags:
                flags[listing.listing_id] = listing_flags
        return kept, flags

    def _evaluate_listing(self, listing: RankingListing, search_spec: SearchSpecModel) -> Tuple[bool, List[str]]:
        flags: List[str] = []
        hard = search_spec.hard
        threshold = self._config.hard_confidence_threshold

        if hard.neighborhoods_include and listing.neighborhood not in hard.neighborhoods_include:
            return False, ["neighborhood_excluded"]
        if listing.neighborhood in hard.neighborhoods_exclude:
            return False, ["neighborhood_excluded"]

        price_field = listing.fields.get("price")
        if hard.price_min is not None or hard.price_max is not None:
            passes, flag = _numeric_constraint(
                price_field,
                min_value=hard.price_min,
                max_value=hard.price_max,
                threshold=threshold,
                label="price",
            )
            if not passes:
                return False, [flag]
            if flag:
                flags.append(flag)

        beds_field = listing.fields.get("beds")
        if hard.beds_min is not None:
            passes, flag = _numeric_constraint(
                beds_field,
                min_value=hard.beds_min,
                max_value=None,
                threshold=threshold,
                label="beds",
            )
            if not passes:
                return False, [flag]
            if flag:
                flags.append(flag)

        baths_field = listing.fields.get("baths")
        if hard.baths_min is not None:
            passes, flag = _numeric_constraint(
                baths_field,
                min_value=hard.baths_min,
                max_value=None,
                threshold=threshold,
                label="baths",
            )
            if not passes:
                return False, [flag]
            if flag:
                flags.append(flag)

        for commute in hard.commute_max:
            commute_value = listing.commutes.get(commute.target_label)
            if commute_value is None or commute_value.mode != commute.mode.value:
                flags.append(f"commute_missing:{commute.target_label}")
                continue
            if commute_value.duration_min > commute.max_min:
                if commute_value.confidence >= threshold:
                    return False, [f"commute_exceeds:{commute.target_label}"]
                flags.append(f"commute_low_confidence:{commute.target_label}")

        availability_field = listing.fields.get("availability")
        if hard.available_now:
            passes, flag = _availability_constraint(
                availability_field,
                latest=search_spec.created_at.date(),
                earliest=None,
                threshold=threshold,
                label="available_now",
                reference_date=search_spec.created_at.date(),
            )
            if not passes:
                return False, [flag]
            if flag:
                flags.append(flag)

        if hard.move_in_after is not None:
            passes, flag = _availability_constraint(
                availability_field,
                latest=None,
                earliest=hard.move_in_after,
                threshold=threshold,
                label="move_in_after",
                reference_date=search_spec.created_at.date(),
            )
            if not passes:
                return False, [flag]
            if flag:
                flags.append(flag)

        for feature in hard.must_have:
            present, confidence = _feature_match(listing, feature)
            if present is None:
                flags.append(f"feature_missing:{feature}")
                continue
            if not present:
                if (confidence or 0.0) >= threshold:
                    return False, [f"feature_missing:{feature}"]
                flags.append(f"feature_low_confidence:{feature}")

        for feature in hard.exclude:
            present, confidence = _feature_match(listing, feature)
            if present is None:
                continue
            if present:
                if (confidence or 0.0) >= threshold:
                    return False, [f"feature_excluded:{feature}"]
                flags.append(f"feature_low_confidence:{feature}")

        return True, flags

    def _score(self, listing: RankingListing, search_spec: SearchSpecModel, flags: List[str]) -> RankedListing:
        utility = 0.0
        confidence_values: List[float] = []
        hard = search_spec.hard
        price_field = listing.fields.get("price")
        if price_field and hard.price_max:
            try:
                price_val, price_confidence = _resolve_structured_field(price_field)
                price_val = float(price_val)
                utility += max(0.0, 1.0 - (price_val / hard.price_max))
            except (TypeError, ValueError):
                pass
            confidence_values.append(price_confidence)

        beds_field = listing.fields.get("beds")
        if beds_field and hard.beds_min is not None:
            try:
                beds_val, beds_confidence = _resolve_structured_field(beds_field)
                utility += 0.5 if float(beds_val) >= hard.beds_min else 0.0
                confidence_values.append(beds_confidence)
            except (TypeError, ValueError):
                pass

        baths_field = listing.fields.get("baths")
        if baths_field and hard.baths_min is not None:
            try:
                baths_val, baths_confidence = _resolve_structured_field(baths_field)
                utility += 0.25 if float(baths_val) >= hard.baths_min else 0.0
                confidence_values.append(baths_confidence)
            except (TypeError, ValueError):
                pass

        for commute in hard.commute_max:
            commute_value = listing.commutes.get(commute.target_label)
            if commute_value:
                utility += max(0.0, 1.0 - (commute_value.duration_min / max(commute.max_min, 1.0)))
                confidence_values.append(commute_value.confidence)

        confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.5
        final = round(utility * confidence, 4)
        explanation = RankingExplanation(
            why=["Structured match"],
            tradeoffs=["Review commute and price confidence"],
            verify=["Verify availability"],
            flags=flags,
        )
        return RankedListing(
            listing_id=listing.listing_id,
            rank=0,
            scores=RankingScores(utility=round(utility, 4), confidence=round(confidence, 4), final=final),
            explanation=explanation,
        )

    def _build_rerank_payload(self, listings: List[RankingListing]) -> List[Dict[str, object]]:
        payload: List[Dict[str, object]] = []
        for listing in listings:
            fields = []
            allowed_fields = [
                name
                for name in sorted(listing.fields.keys())
                if name not in self._config.blocked_rerank_fields
            ]
            for name in allowed_fields[: self._config.max_fields_for_rerank]:
                field = listing.fields[name]
                value, confidence = _resolve_structured_field(field)
                if isinstance(value, str) and len(value) > self._config.max_text_length_for_rerank:
                    continue
                evidence = sorted(
                    field.evidence,
                    key=lambda ev: (ev.evidence_id, ev.fact_id or ""),
                )[: self._config.max_evidence_per_field]
                fields.append(
                    {
                        "field": name,
                        "value": value,
                        "confidence": confidence,
                        "evidence": [
                            {"evidence_id": ev.evidence_id, "fact_id": ev.fact_id}
                            for ev in evidence
                        ],
                    }
                )
            payload.append(
                {
                    "listing_id": listing.listing_id,
                    "fields": fields,
                    "commutes": [
                        {
                            "anchor_id": commute.anchor_id,
                            "mode": commute.mode,
                            "duration_min": commute.duration_min,
                            "confidence": commute.confidence,
                        }
                        for commute in listing.commutes.values()
                    ],
                }
            )
        return payload

    def _apply_diversity_caps(
        self,
        scored: List[RankedListing],
        caps: DiversityCaps,
    ) -> List[RankedListing]:
        building_counts: Dict[str, int] = {}
        neighborhood_counts: Dict[str, int] = {}
        source_counts: Dict[str, int] = {}
        final: List[RankedListing] = []
        listing_lookup: Dict[str, ListingDocument] = {listing.listing_id: listing for listing in self._listings.list()}
        for item in scored:
            listing = listing_lookup.get(item.listing_id)
            if listing is None:
                final.append(item)
                continue
            building_counts.setdefault(listing.building_id, 0)
            neighborhood_counts.setdefault(listing.neighborhood, 0)
            source_counts.setdefault(listing.source_id, 0)
            if building_counts[listing.building_id] >= caps.per_building:
                continue
            if neighborhood_counts[listing.neighborhood] >= caps.per_neighborhood:
                continue
            if source_counts[listing.source_id] >= caps.per_source:
                continue
            building_counts[listing.building_id] += 1
            neighborhood_counts[listing.neighborhood] += 1
            source_counts[listing.source_id] += 1
            final.append(item)
        return final


def _numeric_constraint(
    field: Optional[StructuredField],
    *,
    min_value: Optional[float],
    max_value: Optional[float],
    threshold: float,
    label: str,
) -> Tuple[bool, str]:
    if field is None:
        return True, f"{label}_missing"
    value_raw, confidence = _resolve_structured_field(field)
    try:
        value = float(value_raw)
    except (TypeError, ValueError):
        return True, f"{label}_invalid"
    if min_value is not None and value < min_value:
        if (confidence or 0.0) >= threshold:
            return False, f"{label}_below_min"
        return True, f"{label}_low_confidence"
    if max_value is not None and value > max_value:
        if (confidence or 0.0) >= threshold:
            return False, f"{label}_above_max"
        return True, f"{label}_low_confidence"
    return True, ""


def _resolve_structured_field(field: Optional[StructuredField]) -> Tuple[Optional[object], float]:
    if field is None:
        return None, 0.0
    value = field.value
    confidence = field.confidence or 0.0
    if isinstance(value, list) and value:
        candidates: List[Tuple[object, float]] = []
        for item in value:
            if isinstance(item, dict) and "value" in item:
                item_conf = item.get("confidence", confidence)
                candidates.append((item.get("value"), float(item_conf or 0.0)))
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                item_val, item_conf = item
                try:
                    item_conf_val = float(item_conf)
                except (TypeError, ValueError):
                    item_conf_val = confidence
                candidates.append((item_val, item_conf_val))
            else:
                candidates.append((item, confidence))
        candidates.sort(key=lambda pair: (-(pair[1] or 0.0), str(pair[0])))
        value, confidence = candidates[0]
    return value, confidence


def _feature_match(listing: RankingListing, feature: str) -> Tuple[Optional[bool], Optional[float]]:
    feature_key = feature.strip().lower()
    normalized_keys = {
        feature_key,
        feature_key.replace(" ", "_"),
        feature_key.replace("_", " "),
    }
    for key in normalized_keys:
        field = listing.fields.get(key)
        if field is None:
            continue
        value, confidence = _resolve_structured_field(field)
        return _truthy(value), confidence

    for key in ("amenities", "amenity", "features"):
        field = listing.fields.get(key)
        if field is None:
            continue
        value, confidence = _resolve_structured_field(field)
        items: List[str] = []
        if isinstance(value, str):
            items = [part.strip().lower().replace(" ", "_") for part in value.split(",") if part.strip()]
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    items.append(item.strip().lower().replace(" ", "_"))
                elif isinstance(item, dict) and "value" in item:
                    items.append(str(item["value"]).strip().lower().replace(" ", "_"))
        if items:
            return feature_key in items, confidence
        return _truthy(value), confidence

    return None, None


def _truthy(value: Optional[object]) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"yes", "true", "1", "y", "available", "included", "present"}:
            return True
        if normalized in {"no", "false", "0", "n", "not available", "unavailable", "absent"}:
            return False
    return None


def _availability_constraint(
    field: Optional[StructuredField],
    *,
    earliest: Optional[date],
    latest: Optional[date],
    threshold: float,
    label: str,
    reference_date: date,
) -> Tuple[bool, str]:
    if field is None:
        return True, f"{label}_missing"
    value_raw, confidence = _resolve_structured_field(field)
    if value_raw is None:
        return True, f"{label}_missing"
    value_date = _parse_availability_date(value_raw, reference_date)
    if value_date is None:
        return True, f"{label}_invalid"
    if earliest is not None and value_date < earliest:
        if (confidence or 0.0) >= threshold:
            return False, f"{label}_before_min"
        return True, f"{label}_low_confidence"
    if latest is not None and value_date > latest:
        if (confidence or 0.0) >= threshold:
            return False, f"{label}_after_max"
        return True, f"{label}_low_confidence"
    return True, ""


def _parse_availability_date(value: object, reference_date: date) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"now", "immediate", "available", "available now"}:
            return reference_date
        if not normalized:
            return None
        try:
            return datetime.fromisoformat(normalized).date()
        except ValueError:
            return None
    return None


def _to_ranking_listing(doc: ListingDocument) -> RankingListing:
    fields = {}
    for key, value in doc.structured.items():
        evidence = [EvidenceRef(evidence_id=ev.evidence_id, fact_id=ev.fact_id) for ev in value.evidence]
        fields[key] = StructuredField(value=value.value, confidence=value.confidence, evidence=evidence)
    commutes = {}
    for key, commute in doc.commutes.items():
        commutes[key] = CommuteValue(
            anchor_id=commute.anchor_id,
            mode=commute.mode,
            duration_min=commute.duration_min,
            confidence=commute.confidence,
        )
    return RankingListing(
        listing_id=doc.listing_id,
        building_id=doc.building_id,
        neighborhood=doc.neighborhood,
        source_id=doc.source_id,
        fields=fields,
        commutes=commutes,
    )
