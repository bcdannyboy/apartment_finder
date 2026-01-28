from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from services.searchspec.models import SearchSpecModel
from services.searchspec.parser import SearchSpecParseResult, SearchSpecParser
from services.searchspec.repository import SearchSpecRecord, SearchSpecRepository


@dataclass(frozen=True)
class SearchSpecServiceResult:
    record: Optional[SearchSpecRecord]
    errors: list[Dict[str, Any]]


class SearchSpecService:
    def __init__(self, repository: SearchSpecRepository, parser: Optional[SearchSpecParser] = None) -> None:
        self._repository = repository
        self._parser = parser or SearchSpecParser()

    def create_from_payload(self, payload: Dict[str, Any]) -> SearchSpecServiceResult:
        result: SearchSpecParseResult = self._parser.parse(payload)
        if result.errors or result.spec is None:
            return SearchSpecServiceResult(record=None, errors=result.errors)
        record = self._repository.add(result.spec)
        return SearchSpecServiceResult(record=record, errors=[])

    def get(self, search_spec_id: str) -> Optional[SearchSpecModel]:
        record = self._repository.get(search_spec_id)
        if record is None:
            return None
        return record.spec
