from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Protocol, Tuple

from services.retrieval.models import (
    ListingDocument,
    RetrievalAuditEvent,
    RetrievalCandidate,
    RetrievalQuery,
    RetrievalResult,
)
from services.retrieval.repository import ListingRepository


TOKEN_RE = re.compile(r"\w+")


class ExternalSearchAdapter(Protocol):
    def search(self, query: str, *, limit: int) -> List[Tuple[str, float]]: ...


@dataclass(frozen=True)
class RetrievalConfig:
    title_weight: float = 2.0
    body_weight: float = 1.0
    vector_weight: float = 1.0
    external_weight: float = 1.0
    allow_external: bool = True


class RetrievalService:
    def __init__(
        self,
        repository: ListingRepository,
        *,
        config: Optional[RetrievalConfig] = None,
        external_adapter: Optional[ExternalSearchAdapter] = None,
    ) -> None:
        self._repository = repository
        self._config = config or RetrievalConfig()
        self._external_adapter = external_adapter

    def retrieve(self, query: RetrievalQuery, *, limit: int) -> RetrievalResult:
        audit: List[RetrievalAuditEvent] = []
        candidates: Dict[str, RetrievalCandidate] = {}
        listings = self._repository.list()

        if query.keywords:
            fts_scores = self._fts_scores(listings, query.keywords)
            audit.append(RetrievalAuditEvent(layer="fts", details={"keywords": query.keywords}))
            for listing_id, score in fts_scores.items():
                candidates[listing_id] = self._merge_candidate(
                    listing_id,
                    candidates.get(listing_id),
                    fts_score=score,
                )

        if query.vector is not None:
            vector_scores = self._vector_scores(listings, query.vector)
            audit.append(RetrievalAuditEvent(layer="vector", details={"dimension": len(query.vector)}))
            for listing_id, score in vector_scores.items():
                candidates[listing_id] = self._merge_candidate(
                    listing_id,
                    candidates.get(listing_id),
                    vector_score=score,
                )

        if query.external_query and self._config.allow_external and self._external_adapter:
            external_results = self._external_adapter.search(query.external_query, limit=limit)
            audit.append(RetrievalAuditEvent(layer="external", details={"query": query.external_query}))
            for listing_id, score in external_results:
                candidates[listing_id] = self._merge_candidate(
                    listing_id,
                    candidates.get(listing_id),
                    external_score=score,
                )

        merged = [self._finalize_candidate(candidate) for candidate in candidates.values()]
        ordered = sorted(
            merged,
            key=lambda item: (-item.combined_score, item.listing_id),
        )
        return RetrievalResult(candidates=ordered[:limit], audit_events=audit)

    def _fts_scores(self, listings: Iterable[ListingDocument], keywords: List[str]) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        for listing in listings:
            title_tokens = _tokenize(listing.title)
            body_tokens = _tokenize(listing.body)
            title_count = sum(title_tokens.count(token) for token in keywords)
            body_count = sum(body_tokens.count(token) for token in keywords)
            score = title_count * self._config.title_weight + body_count * self._config.body_weight
            if score > 0:
                scores[listing.listing_id] = score
        return scores

    def _vector_scores(self, listings: Iterable[ListingDocument], vector: List[float]) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        for listing in listings:
            if listing.embedding is None:
                continue
            similarity = _cosine_similarity(vector, listing.embedding)
            scores[listing.listing_id] = similarity * self._config.vector_weight
        return scores

    def _merge_candidate(
        self,
        listing_id: str,
        existing: Optional[RetrievalCandidate],
        *,
        fts_score: Optional[float] = None,
        vector_score: Optional[float] = None,
        external_score: Optional[float] = None,
    ) -> RetrievalCandidate:
        if existing is None:
            existing = RetrievalCandidate(listing_id=listing_id)
        return RetrievalCandidate(
            listing_id=existing.listing_id or listing_id,
            fts_score=fts_score if fts_score is not None else existing.fts_score,
            vector_score=vector_score if vector_score is not None else existing.vector_score,
            external_score=external_score if external_score is not None else existing.external_score,
            combined_score=0.0,
        )

    def _finalize_candidate(self, candidate: RetrievalCandidate) -> RetrievalCandidate:
        combined = candidate.fts_score + candidate.vector_score + candidate.external_score
        return RetrievalCandidate(
            listing_id=candidate.listing_id,
            fts_score=candidate.fts_score,
            vector_score=candidate.vector_score,
            external_score=candidate.external_score,
            combined_score=combined,
        )


def _tokenize(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "")]


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(l * r for l, r in zip(left, right))
    left_norm = math.sqrt(sum(l * l for l in left))
    right_norm = math.sqrt(sum(r * r for r in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
