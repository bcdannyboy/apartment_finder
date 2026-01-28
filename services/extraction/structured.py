from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from services.common.hashes import sha256_text


class EvidenceRefModel(BaseModel):
    snapshot_id: str
    kind: str
    locator: Dict[str, Any]
    excerpt: Optional[str] = None


class FieldValueModel(BaseModel):
    value: Optional[Any] = None
    confidence: Optional[float] = None
    evidence: List[EvidenceRefModel] = Field(default_factory=list)


class StructuredListing(BaseModel):
    address: Optional[FieldValueModel] = None
    address_candidates: List[FieldValueModel] = Field(default_factory=list)
    price: Optional[FieldValueModel] = None
    price_candidates: List[FieldValueModel] = Field(default_factory=list)
    beds: Optional[FieldValueModel] = None
    baths: Optional[FieldValueModel] = None
    availability: Optional[FieldValueModel] = None


class StructuredUnit(BaseModel):
    unit_label: Optional[FieldValueModel] = None
    unit_label_candidates: List[FieldValueModel] = Field(default_factory=list)
    price: Optional[FieldValueModel] = None
    price_candidates: List[FieldValueModel] = Field(default_factory=list)
    beds: Optional[FieldValueModel] = None
    baths: Optional[FieldValueModel] = None


class AmenityItem(BaseModel):
    name: FieldValueModel


class StructuredOutputModel(BaseModel):
    schema_version: str
    listing: StructuredListing
    units: List[StructuredUnit] = Field(default_factory=list)
    amenities: List[AmenityItem] = Field(default_factory=list)


@dataclass(frozen=True)
class StructuredValidationResult:
    extracted_json: Optional[Dict[str, Any]]
    model: Optional[StructuredOutputModel]
    validation_report: Dict[str, Any]


_EXPECTED_TYPES = {
    "/listing/address": (str,),
    "/listing/availability": (str,),
    "/listing/price": (str, int, float),
    "/listing/beds": (int, float),
    "/listing/baths": (int, float),
    "/units/unit_label": (str,),
    "/units/price": (str, int, float),
    "/units/beds": (int, float),
    "/units/baths": (int, float),
    "/amenities/name": (str,),
}


def _error_entry(code: str, message: str, path: str, expected: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "code": code,
        "message": message,
        "path": path,
        "severity": "error",
    }
    if expected:
        payload["expected"] = expected
    return payload


class StructuredOutputValidator:
    def __init__(self, schema_version: str = "v1") -> None:
        self._schema_version = schema_version

    def validate(
        self,
        raw_output: Dict[str, Any],
        *,
        repair_attempts: Optional[List[Dict[str, Any]]] = None,
        max_retries: int = 0,
    ) -> StructuredValidationResult:
        attempts = [raw_output]
        if repair_attempts and max_retries > 0:
            attempts.extend(repair_attempts[:max_retries])
        retry_count = 0
        last_errors: List[Dict[str, Any]] = []

        for index, attempt in enumerate(attempts):
            if index > 0:
                retry_count += 1
            model, errors = self._validate_once(attempt)
            if not errors:
                report = {
                    "schema_version": self._schema_version,
                    "status": "success",
                    "retry_count": retry_count,
                    "errors": [],
                }
                return StructuredValidationResult(
                    extracted_json=model.model_dump(),
                    model=model,
                    validation_report=report,
                )
            last_errors = errors

        report = {
            "schema_version": self._schema_version,
            "status": "failure",
            "retry_count": retry_count,
            "errors": last_errors,
            "raw_output_hash": self._raw_hash(raw_output),
        }
        return StructuredValidationResult(
            extracted_json=None,
            model=None,
            validation_report=report,
        )

    def _validate_once(
        self, payload: Dict[str, Any]
    ) -> tuple[Optional[StructuredOutputModel], List[Dict[str, Any]]]:
        errors: List[Dict[str, Any]] = []
        try:
            model = StructuredOutputModel.model_validate(payload)
        except ValidationError as exc:
            for err in exc.errors():
                path = "/" + "/".join(str(item) for item in err.get("loc", []))
                errors.append(
                    _error_entry("schema_error", err.get("msg", "invalid"), path)
                )
            return None, errors
        if model.schema_version != self._schema_version:
            errors.append(
                _error_entry(
                    "schema_version_mismatch",
                    f"schema_version must be {self._schema_version}",
                    "/schema_version",
                )
            )
            return None, errors
        errors.extend(self._type_errors(model))
        if errors:
            return None, errors
        return model, []

    def _type_errors(self, model: StructuredOutputModel) -> List[Dict[str, Any]]:
        errors: List[Dict[str, Any]] = []

        def check(field: Optional[FieldValueModel], path: str) -> None:
            if field is None or field.value is None:
                return
            expected = _EXPECTED_TYPES.get(path)
            if expected is None:
                return
            if not isinstance(field.value, expected):
                expected_names = ", ".join(t.__name__ for t in expected)
                errors.append(
                    _error_entry(
                        "type_mismatch",
                        f"value must be of type {expected_names}",
                        path,
                        expected=expected_names,
                    )
                )

        listing = model.listing
        check(listing.address, "/listing/address")
        for candidate in listing.address_candidates:
            check(candidate, "/listing/address")
        check(listing.price, "/listing/price")
        for candidate in listing.price_candidates:
            check(candidate, "/listing/price")
        check(listing.beds, "/listing/beds")
        check(listing.baths, "/listing/baths")
        check(listing.availability, "/listing/availability")

        for unit in model.units:
            check(unit.unit_label, "/units/unit_label")
            for candidate in unit.unit_label_candidates:
                check(candidate, "/units/unit_label")
            check(unit.price, "/units/price")
            for candidate in unit.price_candidates:
                check(candidate, "/units/price")
            check(unit.beds, "/units/beds")
            check(unit.baths, "/units/baths")

        for amenity in model.amenities:
            check(amenity.name, "/amenities/name")

        return errors

    @staticmethod
    def _raw_hash(payload: Dict[str, Any]) -> str:
        try:
            raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        except TypeError:
            raw = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
        return sha256_text(raw)
