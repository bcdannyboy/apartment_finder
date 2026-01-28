from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from services.retrieval.models import ListingDocument
from services.retrieval.utils import cosine_similarity, tokenize


class ListingRepository:
    def __init__(self) -> None:
        self._listings: Dict[str, ListingDocument] = {}

    def add(self, listing: ListingDocument) -> None:
        self._listings[listing.listing_id] = listing

    def get(self, listing_id: str) -> Optional[ListingDocument]:
        return self._listings.get(listing_id)

    def list(self) -> List[ListingDocument]:
        return list(self._listings.values())

    def fts_search(
        self,
        keywords: List[str],
        *,
        limit: int,
        title_weight: float,
        body_weight: float,
    ) -> List[Tuple[str, float]]:
        if not keywords:
            return []
        scores: Dict[str, float] = {}
        for listing in self._listings.values():
            title_tokens = tokenize(listing.title)
            body_tokens = tokenize(listing.body)
            title_count = sum(title_tokens.count(token) for token in keywords)
            body_count = sum(body_tokens.count(token) for token in keywords)
            score = title_count * title_weight + body_count * body_weight
            if score > 0:
                scores[listing.listing_id] = score
        ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return ordered[:limit]

    def vector_search(self, vector: List[float], *, limit: int) -> List[Tuple[str, float]]:
        if not vector:
            return []
        scores: Dict[str, float] = {}
        for listing in self._listings.values():
            if listing.embedding is None:
                continue
            similarity = cosine_similarity(vector, listing.embedding)
            scores[listing.listing_id] = similarity
        ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return ordered[:limit]
