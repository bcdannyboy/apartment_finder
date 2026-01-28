from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from services.common.enums import CommuteMode, GeoProvider, RoutingProvider


class GeocodePrecision(str, Enum):
    rooftop = "rooftop"
    parcel = "parcel"
    interpolated = "interpolated"
    centroid = "centroid"
    locality = "locality"
    region = "region"


class GeoCommuteError(RuntimeError):
    def __init__(self, message: str, *, code: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


class GeocodeError(GeoCommuteError):
    def __init__(self, message: str, *, code: str = "GEOCODE_ERROR", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, code=code, details=details)


class RoutingError(GeoCommuteError):
    def __init__(self, message: str, *, code: str = "ROUTING_ERROR", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, code=code, details=details)


@dataclass(frozen=True)
class GeocodeRequest:
    address: str
    locality: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None


@dataclass(frozen=True)
class GeocodeResult:
    latitude: float
    longitude: float
    precision: GeocodePrecision
    confidence: float
    provider: GeoProvider
    label: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RouteRequest:
    origin_latitude: float
    origin_longitude: float
    destination_latitude: float
    destination_longitude: float
    mode: CommuteMode
    depart_at: datetime


@dataclass(frozen=True)
class RouteResult:
    duration_min: float
    distance_m: float
    provider: RoutingProvider
    mode: CommuteMode
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommuteRequest(RouteRequest):
    origin_h3: str
    anchor_id: str
    gtfs_fingerprint: Optional[str] = None


@dataclass(frozen=True)
class CommuteResult:
    cache_key: str
    cache_hit: bool
    route: RouteResult


def ensure_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
