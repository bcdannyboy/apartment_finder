from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from services.common.enums import CommuteMode, GeoProvider, RoutingProvider
from services.geo_commute.models import GeocodePrecision


class GeocodeRequestModel(BaseModel):
    schema_version: str
    address: str
    locality: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None


class GeocodeResponseModel(BaseModel):
    provider: GeoProvider
    precision: GeocodePrecision
    confidence: float
    latitude: float
    longitude: float
    label: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CommuteRequestModel(BaseModel):
    schema_version: str
    origin_latitude: float
    origin_longitude: float
    destination_latitude: float
    destination_longitude: float
    mode: CommuteMode
    depart_at: datetime
    origin_h3: str
    anchor_id: str
    gtfs_fingerprint: Optional[str] = None


class RouteResponseModel(BaseModel):
    duration_min: float
    distance_m: float
    provider: RoutingProvider
    mode: CommuteMode
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CommuteResponseModel(BaseModel):
    cache_key: str
    cache_hit: bool
    route: RouteResponseModel


class GtfsRegisterRequestModel(BaseModel):
    schema_version: str
    path: str
    fingerprint: str


class GtfsRegisterResponseModel(BaseModel):
    fingerprint: str
    graph_version: str
