from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from services.searchspec.models import SearchSpecModel


@dataclass(frozen=True)
class SearchSpecRecord:
    spec: SearchSpecModel


class SearchSpecRepository:
    def __init__(self) -> None:
        self._specs: Dict[str, SearchSpecRecord] = {}

    def add(self, spec: SearchSpecModel) -> SearchSpecRecord:
        record = SearchSpecRecord(spec=spec)
        self._specs[spec.search_spec_id] = record
        return record

    def get(self, search_spec_id: str) -> Optional[SearchSpecRecord]:
        return self._specs.get(search_spec_id)

    def list(self) -> List[SearchSpecRecord]:
        return list(self._specs.values())
