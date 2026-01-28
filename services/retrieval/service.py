from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from services.retrieval.models import RetrievalAuditEvent, RetrievalCandidate, RetrievalQuery, RetrievalResult
from services.retrieval.repository import ListingRepository


@dataclass(frozen=True)
class RetrievalConfig:
    title_weight: float = 2.0
    body_weight: float = 1.0
    vector_weight: float = 1.0


class RetrievalService:
    def __init__(
        self,
        repository: ListingRepository,
        *,
        config: Optional[RetrievalConfig] = None,
    ) -> None:
        self._repository = repository
        self._config = config or RetrievalConfig()

    def retrieve(self, query: RetrievalQuery, *, limit: int) -> RetrievalResult:
        audit: List[RetrievalAuditEvent] = []
        candidates: Dict[str, RetrievalCandidate] = {}

        if query.keywords:
            fts_results = self._repository.fts_search(
                query.keywords,
                limit=limit,
                title_weight=self._config.title_weight,
                body_weight=self._config.body_weight,
            )
            audit.append(RetrievalAuditEvent(layer="fts", details={"keywords": query.keywords}))
            for listing_id, score in fts_results:
                candidates[listing_id] = self._merge_candidate(
                    listing_id,
                    candidates.get(listing_id),
                    fts_score=score,
                )

        if query.vector is not None:
            vector_results = self._repository.vector_search(query.vector, limit=limit)
            audit.append(RetrievalAuditEvent(layer="vector", details={"dimension": len(query.vector)}))
            for listing_id, score in vector_results:
                candidates[listing_id] = self._merge_candidate(
                    listing_id,
                    candidates.get(listing_id),
                    vector_score=score * self._config.vector_weight,
                )

        merged = [self._finalize_candidate(candidate) for candidate in candidates.values()]
        ordered = sorted(
            merged,
            key=lambda item: (-item.combined_score, item.listing_id),
        )
        return RetrievalResult(candidates=ordered[:limit], audit_events=audit)

    def _merge_candidate(
        self,
        listing_id: str,
        existing: Optional[RetrievalCandidate],
        *,
        fts_score: Optional[float] = None,
        vector_score: Optional[float] = None,
    ) -> RetrievalCandidate:
        if existing is None:
            existing = RetrievalCandidate(listing_id=listing_id)
        return RetrievalCandidate(
            listing_id=existing.listing_id or listing_id,
            fts_score=fts_score if fts_score is not None else existing.fts_score,
            vector_score=vector_score if vector_score is not None else existing.vector_score,
            combined_score=0.0,
        )

    def _finalize_candidate(self, candidate: RetrievalCandidate) -> RetrievalCandidate:
        combined = candidate.fts_score + candidate.vector_score
        return RetrievalCandidate(
            listing_id=candidate.listing_id,
            fts_score=candidate.fts_score,
            vector_score=candidate.vector_score,
            combined_score=combined,
        )
