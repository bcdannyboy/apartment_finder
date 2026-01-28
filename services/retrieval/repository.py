from __future__ import annotations

from typing import Dict, List, Optional

from services.retrieval.models import ListingDocument


class ListingRepository:
    def __init__(self) -> None:
        self._listings: Dict[str, ListingDocument] = {}

    def add(self, listing: ListingDocument) -> None:
        self._listings[listing.listing_id] = listing

    def get(self, listing_id: str) -> Optional[ListingDocument]:
        return self._listings.get(listing_id)

    def list(self) -> List[ListingDocument]:
        return list(self._listings.values())
