from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from pydantic import ValidationError

from services.searchspec.models import (
    CommuteMaxModel,
    SearchSpecExplorationModel,
    SearchSpecHardModel,
    SearchSpecModel,
    SearchSpecSoftModel,
)


DEFAULT_NEIGHBORHOODS = {
    "mission",
    "soma",
    "sunset",
    "noe valley",
    "haight",
    "richmond",
}

DEFAULT_NEIGHBORHOOD_ALIASES = {
    "mission district": "mission",
    "south of market": "soma",
    "so ma": "soma",
    "haight-ashbury": "haight",
    "noe": "noe valley",
}

DEFAULT_FEATURE_ALIASES = {
    "in unit laundry": "in_unit_laundry",
    "laundry": "in_unit_laundry",
    "parking": "parking",
    "pet friendly": "pet_friendly",
}


@dataclass(frozen=True)
class SearchSpecParseResult:
    spec: Optional[SearchSpecModel]
    errors: List[Dict[str, Any]]


class SearchSpecParser:
    def __init__(
        self,
        *,
        schema_version: str = "v1",
        known_neighborhoods: Optional[Iterable[str]] = None,
        neighborhood_aliases: Optional[Dict[str, str]] = None,
        feature_aliases: Optional[Dict[str, str]] = None,
    ) -> None:
        self._schema_version = schema_version
        self._known_neighborhoods = set(
            name.strip().lower() for name in (known_neighborhoods or DEFAULT_NEIGHBORHOODS)
        )
        self._neighborhood_aliases = {
            key.strip().lower(): value.strip().lower()
            for key, value in (neighborhood_aliases or DEFAULT_NEIGHBORHOOD_ALIASES).items()
        }
        self._feature_aliases = {
            key.strip().lower(): value for key, value in (feature_aliases or DEFAULT_FEATURE_ALIASES).items()
        }

    def parse(self, payload: Dict[str, Any]) -> SearchSpecParseResult:
        errors: List[Dict[str, Any]] = []
        try:
            spec = SearchSpecModel.model_validate(payload)
        except ValidationError as exc:
            for err in exc.errors():
                path = "/" + "/".join(str(item) for item in err.get("loc", []))
                errors.append(
                    {
                        "code": "schema_error",
                        "message": err.get("msg", "invalid"),
                        "path": path,
                    }
                )
            return SearchSpecParseResult(spec=None, errors=errors)

        if spec.schema_version != self._schema_version:
            errors.append(
                {
                    "code": "schema_version_mismatch",
                    "message": f"schema_version must be {self._schema_version}",
                    "path": "/schema_version",
                }
            )
            return SearchSpecParseResult(spec=None, errors=errors)

        spec = self._normalize(spec)
        errors.extend(self._validate_constraints(spec))
        if errors:
            return SearchSpecParseResult(spec=None, errors=errors)
        return SearchSpecParseResult(spec=spec, errors=[])

    def _normalize(self, spec: SearchSpecModel) -> SearchSpecModel:
        spec.search_spec_id = spec.search_spec_id or str(uuid4())
        spec.created_at = spec.created_at or datetime.now(tz=timezone.utc)
        spec.raw_prompt = self._normalize_text(spec.raw_prompt)

        hard = spec.hard
        hard.neighborhoods_include = self._normalize_neighborhoods(hard.neighborhoods_include)
        hard.neighborhoods_exclude = self._normalize_neighborhoods(hard.neighborhoods_exclude)
        hard.must_have = self._normalize_features(hard.must_have)
        hard.exclude = self._normalize_features(hard.exclude)
        hard.commute_max = [
            CommuteMaxModel(
                target_label=self._normalize_text(item.target_label) or "",
                mode=item.mode,
                max_min=item.max_min,
            )
            for item in hard.commute_max
        ]

        soft = spec.soft
        soft.nice_to_have = self._normalize_features(soft.nice_to_have)
        soft.vibe = [self._normalize_text(val) or "" for val in soft.vibe]
        soft.weights = {self._normalize_text(key) or "": value for key, value in soft.weights.items()}

        exploration = spec.exploration
        exploration.rules = [self._normalize_text(val) or "" for val in exploration.rules]

        spec.hard = hard
        spec.soft = soft
        spec.exploration = exploration
        return spec

    def _normalize_text(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return " ".join(value.strip().lower().split())

    def _normalize_features(self, values: List[str]) -> List[str]:
        normalized: List[str] = []
        for val in values:
            cleaned = self._normalize_text(val)
            if not cleaned:
                continue
            normalized.append(self._feature_aliases.get(cleaned, cleaned.replace(" ", "_")))
        return normalized

    def _normalize_neighborhoods(self, values: List[str]) -> List[str]:
        normalized: List[str] = []
        for val in values:
            cleaned = self._normalize_text(val)
            if not cleaned:
                continue
            canonical = self._neighborhood_aliases.get(cleaned, cleaned)
            normalized.append(canonical)
        return normalized

    def _validate_constraints(self, spec: SearchSpecModel) -> List[Dict[str, Any]]:
        errors: List[Dict[str, Any]] = []
        hard = spec.hard
        if hard.price_min is not None and hard.price_min < 0:
            errors.append(
                {
                    "code": "value_range",
                    "message": "price_min must be non-negative",
                    "path": "/hard/price_min",
                }
            )
        if hard.price_max is not None and hard.price_max < 0:
            errors.append(
                {
                    "code": "value_range",
                    "message": "price_max must be non-negative",
                    "path": "/hard/price_max",
                }
            )
        if hard.price_min is not None and hard.price_max is not None and hard.price_min > hard.price_max:
            errors.append(
                {
                    "code": "value_range",
                    "message": "price_min must be <= price_max",
                    "path": "/hard/price_min",
                }
            )
        if hard.beds_min is not None and hard.beds_min < 0:
            errors.append(
                {
                    "code": "value_range",
                    "message": "beds_min must be non-negative",
                    "path": "/hard/beds_min",
                }
            )
        if hard.baths_min is not None and hard.baths_min < 0:
            errors.append(
                {
                    "code": "value_range",
                    "message": "baths_min must be non-negative",
                    "path": "/hard/baths_min",
                }
            )
        if hard.available_now and hard.move_in_after is not None:
            errors.append(
                {
                    "code": "invalid_combination",
                    "message": "available_now and move_in_after are mutually exclusive",
                    "path": "/hard",
                }
            )
        for entry in hard.commute_max:
            if not entry.target_label:
                errors.append(
                    {
                        "code": "missing_required",
                        "message": "commute_max.target_label is required",
                        "path": "/hard/commute_max",
                    }
                )
            if entry.max_min < 0:
                errors.append(
                    {
                        "code": "value_range",
                        "message": "commute_max.max_min must be non-negative",
                        "path": "/hard/commute_max",
                    }
                )
        for name in hard.neighborhoods_include + hard.neighborhoods_exclude:
            if name and name not in self._known_neighborhoods:
                errors.append(
                    {
                        "code": "unknown_neighborhood",
                        "message": f"Unknown neighborhood: {name}",
                        "path": "/hard/neighborhoods",
                    }
                )
        return errors
