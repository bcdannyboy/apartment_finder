from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from services.common.enums import CommuteMode
from services.common.enums import GeoProvider
from services.geo_commute.models import CommuteRequest, GeocodePrecision, GeocodeRequest, GeocodeResult, RouteResult
from services.geo_commute.service import GeoCommuteService


@dataclass(frozen=True)
class CommuteAnchor:
    anchor_id: str
    latitude: float
    longitude: float
    mode: CommuteMode


@dataclass(frozen=True)
class ListingLocationInput:
    listing_id: str
    address: str
    origin_h3: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@dataclass(frozen=True)
class CommuteTargetResult:
    anchor_id: str
    mode: CommuteMode
    route: RouteResult
    cache_key: str
    cache_hit: bool


@dataclass(frozen=True)
class GeoCommuteEnrichment:
    listing_id: str
    geocode: GeocodeResult
    commutes: List[CommuteTargetResult]


class GeoCommuteEnrichmentService:
    def __init__(self, geo_commute: GeoCommuteService) -> None:
        self._geo_commute = geo_commute

    def enrich(
        self,
        *,
        listing: ListingLocationInput,
        anchors: List[CommuteAnchor],
        depart_at: datetime,
    ) -> GeoCommuteEnrichment:
        if listing.latitude is None or listing.longitude is None:
            geocode = self._geo_commute.geocode_address(
                GeocodeRequest(address=listing.address)
            )
            latitude = geocode.latitude
            longitude = geocode.longitude
        else:
            geocode = GeocodeResult(
                latitude=listing.latitude,
                longitude=listing.longitude,
                precision=GeocodePrecision.centroid,
                confidence=1.0,
                provider=GeoProvider.pelias,
                label=listing.address,
                metadata={"source": "provided_coordinates"},
            )
        commutes: List[CommuteTargetResult] = []
        for anchor in anchors:
            result = self._geo_commute.commute(
                CommuteRequest(
                    origin_latitude=latitude,
                    origin_longitude=longitude,
                    destination_latitude=anchor.latitude,
                    destination_longitude=anchor.longitude,
                    mode=anchor.mode,
                    depart_at=depart_at,
                    origin_h3=listing.origin_h3,
                    anchor_id=anchor.anchor_id,
                )
            )
            commutes.append(
                CommuteTargetResult(
                    anchor_id=anchor.anchor_id,
                    mode=anchor.mode,
                    route=result.route,
                    cache_key=result.cache_key,
                    cache_hit=result.cache_hit,
                )
            )
        return GeoCommuteEnrichment(
            listing_id=listing.listing_id,
            geocode=geocode,
            commutes=commutes,
        )
