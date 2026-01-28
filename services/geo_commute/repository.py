from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List
from uuid import uuid4

from services.geo_commute.models import CommuteRequest, GeocodeRequest, GeocodeResult, RouteResult


@dataclass(frozen=True)
class GeocodeRecord:
    geocode_id: str
    request: GeocodeRequest
    result: GeocodeResult
    created_at: datetime


@dataclass(frozen=True)
class CommuteRecord:
    commute_id: str
    request: CommuteRequest
    route: RouteResult
    cache_key: str
    cache_hit: bool
    created_at: datetime


class GeoCommuteRepository:
    def __init__(self) -> None:
        self._geocodes: List[GeocodeRecord] = []
        self._commutes: List[CommuteRecord] = []

    def add_geocode(self, request: GeocodeRequest, result: GeocodeResult) -> GeocodeRecord:
        record = GeocodeRecord(
            geocode_id=str(uuid4()),
            request=request,
            result=result,
            created_at=datetime.now(tz=timezone.utc),
        )
        self._geocodes.append(record)
        return record

    def add_commute(
        self,
        request: CommuteRequest,
        route: RouteResult,
        *,
        cache_key: str,
        cache_hit: bool,
    ) -> CommuteRecord:
        record = CommuteRecord(
            commute_id=str(uuid4()),
            request=request,
            route=route,
            cache_key=cache_key,
            cache_hit=cache_hit,
            created_at=datetime.now(tz=timezone.utc),
        )
        self._commutes.append(record)
        return record

    def list_geocodes(self) -> List[GeocodeRecord]:
        return list(self._geocodes)

    def list_commutes(self) -> List[CommuteRecord]:
        return list(self._commutes)
