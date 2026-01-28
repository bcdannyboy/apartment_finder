from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass(frozen=True)
class NormalizedFact:
    normalized_fact_id: str
    raw_fact_id: str
    observation_id: str
    field_path: str
    raw_value: Any
    normalized_value: Any
    confidence: Optional[float]
    evidence_ids: List[str]
    normalizer_version: str
