from __future__ import annotations

import re
from typing import Any, Dict, List

from services.common.facts import FactEvidenceLink, FactRecord
from services.extraction.determinism import deterministic_id
from services.normalization.models import NormalizedFact


_PRICE_RE = re.compile(r"\d+(?:,\d+)*(?:\.\d+)?")


def _normalize_price(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = _PRICE_RE.search(value.replace("$", ""))
        if match:
            return float(match.group(0).replace(",", ""))
    return value


def _normalize_float(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value) * 2) / 2
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return value
        return round(parsed * 2) / 2
    return value


def _normalize_address(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    # Preserve fractional components like "1/2" by only collapsing whitespace.
    return " ".join(value.strip().split())


def _evidence_map(links: List[FactEvidenceLink]) -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    for link in links:
        mapping.setdefault(link.fact_id, []).append(link.evidence_id)
    return mapping


class NormalizationService:
    def __init__(self, *, normalizer_version: str = "normalize/v1") -> None:
        self._version = normalizer_version

    def normalize(
        self,
        facts: List[FactRecord],
        links: List[FactEvidenceLink],
    ) -> List[NormalizedFact]:
        evidence_ids = _evidence_map(links)
        normalized: List[NormalizedFact] = []

        for fact in facts:
            if fact.value_json is None:
                continue
            raw_value = fact.value_json
            normalized_value = self._normalize_value(fact.field_path, raw_value)
            normalized_id = deterministic_id(
                "normalized_fact",
                {
                    "raw_fact_id": fact.fact_id,
                    "field_path": fact.field_path,
                    "normalized_value": normalized_value,
                    "version": self._version,
                },
            )
            normalized.append(
                NormalizedFact(
                    normalized_fact_id=normalized_id,
                    raw_fact_id=fact.fact_id,
                    observation_id=fact.observation_id,
                    field_path=fact.field_path,
                    raw_value=raw_value,
                    normalized_value=normalized_value,
                    confidence=fact.confidence,
                    evidence_ids=evidence_ids.get(fact.fact_id, []),
                    normalizer_version=self._version,
                )
            )

        ordered = sorted(
            normalized,
            key=lambda item: (
                item.field_path,
                str(item.raw_value),
                str(item.normalized_value),
                item.raw_fact_id,
            ),
        )
        return ordered

    def _normalize_value(self, field_path: str, value: Any) -> Any:
        if field_path.endswith("/price"):
            return _normalize_price(value)
        if field_path.endswith("/beds") or field_path.endswith("/baths"):
            return _normalize_float(value)
        if field_path.endswith("/address"):
            return _normalize_address(value)
        return value
