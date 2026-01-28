from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from services.common.enums import CommuteMode, GeoProvider, RoutingProvider
from services.common.local_bind import LocalBindError, ensure_local_url
from services.geo_commute.models import (
    GeocodeError,
    GeocodePrecision,
    GeocodeRequest,
    GeocodeResult,
    RouteRequest,
    RouteResult,
    RoutingError,
)


def _normalize_confidence(value: Optional[float], *, default: float = 0.5) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed < 0:
        parsed = 0.0
    if parsed > 1:
        parsed = 1.0
    return round(parsed, 3)


def _normalize_coordinate(value: Any) -> float:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError) as exc:
        raise GeocodeError("Invalid coordinate", details={"value": str(value)}) from exc


class LocalHttpTransport:
    def __init__(
        self,
        *,
        allowed_hosts: Optional[Iterable[str]] = None,
        allow_private_ips: bool = False,
        timeout_s: float = 10.0,
    ) -> None:
        self._allowed_hosts = set(allowed_hosts or [])
        self._allow_private_ips = allow_private_ips
        self._timeout_s = timeout_s

    def request(
        self,
        *,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if params:
            url = f"{url}?{urlencode(params)}"
        ensure_local_url(url, allowed_hosts=self._allowed_hosts, allow_private_ips=self._allow_private_ips)
        data = None
        headers = {}
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        with urlopen(request, timeout=self._timeout_s) as response:  # nosec B310 - local-only enforced
            payload = response.read()
        if not payload:
            return {}
        return json.loads(payload)


class PeliasGeocoder:
    provider = GeoProvider.pelias

    def __init__(
        self,
        *,
        base_url: str,
        transport: Optional[LocalHttpTransport] = None,
        allowed_hosts: Optional[Iterable[str]] = None,
    ) -> None:
        ensure_local_url(base_url, allowed_hosts=allowed_hosts)
        self._base_url = base_url.rstrip("/")
        self._transport = transport or LocalHttpTransport(allowed_hosts=allowed_hosts)

    def geocode(self, request: GeocodeRequest) -> Optional[GeocodeResult]:
        try:
            response = self._transport.request(
                method="GET",
                url=f"{self._base_url}/v1/search",
                params={
                    "text": request.address,
                    "locality": request.locality,
                    "region": request.region,
                    "country": request.country,
                },
            )
        except LocalBindError as exc:
            raise GeocodeError("Pelias URL not local-only") from exc
        except Exception as exc:  # pragma: no cover - unexpected
            raise GeocodeError("Pelias request failed") from exc

        features = response.get("features") or []
        if not features:
            return None
        feature = features[0]
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or [None, None]
        lon = _normalize_coordinate(coordinates[0])
        lat = _normalize_coordinate(coordinates[1])
        properties = feature.get("properties") or {}
        precision = _precision_from_pelias(properties)
        confidence = _normalize_confidence(properties.get("confidence"))
        label = properties.get("label") or properties.get("name")
        return GeocodeResult(
            latitude=lat,
            longitude=lon,
            precision=precision,
            confidence=confidence,
            provider=self.provider,
            label=label,
            metadata={"raw": properties},
        )


class NominatimGeocoder:
    provider = GeoProvider.nominatim

    def __init__(
        self,
        *,
        base_url: str,
        transport: Optional[LocalHttpTransport] = None,
        allowed_hosts: Optional[Iterable[str]] = None,
    ) -> None:
        ensure_local_url(base_url, allowed_hosts=allowed_hosts)
        self._base_url = base_url.rstrip("/")
        self._transport = transport or LocalHttpTransport(allowed_hosts=allowed_hosts)

    def geocode(self, request: GeocodeRequest) -> Optional[GeocodeResult]:
        try:
            response = self._transport.request(
                method="GET",
                url=f"{self._base_url}/search",
                params={
                    "q": request.address,
                    "format": "json",
                    "addressdetails": 1,
                },
            )
        except LocalBindError as exc:
            raise GeocodeError("Nominatim URL not local-only") from exc
        except Exception as exc:  # pragma: no cover - unexpected
            raise GeocodeError("Nominatim request failed") from exc

        if not response:
            return None
        # Nominatim returns a list of results.
        first = response[0] if isinstance(response, list) else None
        if not first:
            return None
        lat = _normalize_coordinate(first.get("lat"))
        lon = _normalize_coordinate(first.get("lon"))
        precision = _precision_from_nominatim(first)
        confidence = _normalize_confidence(first.get("importance"), default=0.4)
        label = first.get("display_name")
        return GeocodeResult(
            latitude=lat,
            longitude=lon,
            precision=precision,
            confidence=confidence,
            provider=self.provider,
            label=label,
            metadata={"raw": first},
        )


def _precision_from_pelias(properties: Dict[str, Any]) -> GeocodePrecision:
    layer = (properties.get("layer") or "").lower()
    if layer in {"address", "venue"}:
        return GeocodePrecision.rooftop
    if layer in {"street", "intersection"}:
        return GeocodePrecision.interpolated
    if layer in {"neighbourhood", "locality"}:
        return GeocodePrecision.locality
    if layer in {"county", "region", "macroregion", "state", "country"}:
        return GeocodePrecision.region
    return GeocodePrecision.centroid


def _precision_from_nominatim(payload: Dict[str, Any]) -> GeocodePrecision:
    addresstype = (payload.get("addresstype") or payload.get("type") or "").lower()
    if addresstype in {"house", "building", "poi", "address"}:
        return GeocodePrecision.rooftop
    if addresstype in {"road", "street"}:
        return GeocodePrecision.interpolated
    if addresstype in {"suburb", "neighbourhood", "city", "town", "village", "locality"}:
        return GeocodePrecision.locality
    if addresstype in {"state", "region", "country"}:
        return GeocodePrecision.region
    return GeocodePrecision.centroid


class OtpRouter:
    provider = RoutingProvider.otp

    def __init__(
        self,
        *,
        base_url: str,
        transport: Optional[LocalHttpTransport] = None,
        allowed_hosts: Optional[Iterable[str]] = None,
        graph_version: Optional[str] = None,
    ) -> None:
        ensure_local_url(base_url, allowed_hosts=allowed_hosts)
        self._base_url = base_url.rstrip("/")
        self._transport = transport or LocalHttpTransport(allowed_hosts=allowed_hosts)
        self._graph_version = graph_version

    @property
    def version_token(self) -> str:
        return f"otp:{self._graph_version or 'unknown'}"

    def set_graph_version(self, version: str) -> None:
        self._graph_version = version

    def route(self, request: RouteRequest) -> RouteResult:
        try:
            response = self._transport.request(
                method="GET",
                url=f"{self._base_url}/otp/routers/default/plan",
                params={
                    "fromLat": request.origin_latitude,
                    "fromLon": request.origin_longitude,
                    "toLat": request.destination_latitude,
                    "toLon": request.destination_longitude,
                    "mode": "TRANSIT",
                },
            )
        except LocalBindError as exc:
            raise RoutingError("OTP URL not local-only") from exc
        except Exception as exc:  # pragma: no cover - unexpected
            raise RoutingError("OTP routing failed") from exc

        plan = response.get("plan") if isinstance(response, dict) else None
        itineraries = plan.get("itineraries") if isinstance(plan, dict) else None
        if not itineraries:
            raise RoutingError("OTP returned no itineraries", code="NO_ROUTE")
        itinerary = itineraries[0]
        duration_min = round(float(itinerary.get("duration", 0)) / 60.0, 2)
        distance_m = round(float(itinerary.get("distance", 0)), 2)
        return RouteResult(
            duration_min=duration_min,
            distance_m=distance_m,
            provider=self.provider,
            mode=request.mode,
            metadata={
                "provider_version": self._graph_version,
                "raw": itinerary,
            },
        )


class ValhallaRouter:
    provider = RoutingProvider.valhalla

    def __init__(
        self,
        *,
        base_url: str,
        transport: Optional[LocalHttpTransport] = None,
        allowed_hosts: Optional[Iterable[str]] = None,
        profile_version: str = "valhalla-profile-v1",
        tiles_version: str = "tiles-v1",
        tiles_available: bool = True,
    ) -> None:
        ensure_local_url(base_url, allowed_hosts=allowed_hosts)
        self._base_url = base_url.rstrip("/")
        self._transport = transport or LocalHttpTransport(allowed_hosts=allowed_hosts)
        self._profile_version = profile_version
        self._tiles_version = tiles_version
        self._tiles_available = tiles_available

    @property
    def version_token(self) -> str:
        return f"valhalla:{self._profile_version}:{self._tiles_version}"

    @property
    def profile_version(self) -> str:
        return self._profile_version

    def set_profile_version(self, value: str) -> None:
        self._profile_version = value

    def route(self, request: RouteRequest) -> RouteResult:
        if not self._tiles_available:
            raise RoutingError("Valhalla tiles missing", code="VALHALLA_TILES_MISSING")
        costing = {
            CommuteMode.walk: "pedestrian",
            CommuteMode.bike: "bicycle",
            CommuteMode.drive: "auto",
        }.get(request.mode)
        if not costing:
            raise RoutingError("Valhalla does not support mode", code="UNSUPPORTED_MODE")
        try:
            response = self._transport.request(
                method="POST",
                url=f"{self._base_url}/route",
                json_body={
                    "locations": [
                        {"lat": request.origin_latitude, "lon": request.origin_longitude},
                        {"lat": request.destination_latitude, "lon": request.destination_longitude},
                    ],
                    "costing": costing,
                },
            )
        except LocalBindError as exc:
            raise RoutingError("Valhalla URL not local-only") from exc
        except Exception as exc:  # pragma: no cover - unexpected
            raise RoutingError("Valhalla routing failed") from exc

        trip = response.get("trip") if isinstance(response, dict) else None
        summary = trip.get("summary") if isinstance(trip, dict) else None
        if not summary:
            raise RoutingError("Valhalla returned no summary", code="NO_ROUTE")
        duration_min = round(float(summary.get("time", 0)) / 60.0, 2)
        distance_m = round(float(summary.get("length", 0)) * 1000.0, 2)
        return RouteResult(
            duration_min=duration_min,
            distance_m=distance_m,
            provider=self.provider,
            mode=request.mode,
            metadata={
                "provider_version": self._profile_version,
                "tiles_version": self._tiles_version,
                "raw": summary,
            },
        )


class OsrmRouter:
    provider = RoutingProvider.osrm

    def __init__(
        self,
        *,
        base_url: str,
        transport: Optional[LocalHttpTransport] = None,
        allowed_hosts: Optional[Iterable[str]] = None,
        profile_version: str = "osrm-profile-v1",
    ) -> None:
        ensure_local_url(base_url, allowed_hosts=allowed_hosts)
        self._base_url = base_url.rstrip("/")
        self._transport = transport or LocalHttpTransport(allowed_hosts=allowed_hosts)
        self._profile_version = profile_version

    @property
    def version_token(self) -> str:
        return f"osrm:{self._profile_version}"

    def route(self, request: RouteRequest) -> RouteResult:
        profile = {
            CommuteMode.walk: "foot",
            CommuteMode.bike: "bike",
            CommuteMode.drive: "driving",
        }.get(request.mode)
        if not profile:
            raise RoutingError("OSRM does not support mode", code="UNSUPPORTED_MODE")
        coordinates = f"{request.origin_longitude},{request.origin_latitude};{request.destination_longitude},{request.destination_latitude}"
        try:
            response = self._transport.request(
                method="GET",
                url=f"{self._base_url}/route/v1/{profile}/{coordinates}",
                params={"overview": "false"},
            )
        except LocalBindError as exc:
            raise RoutingError("OSRM URL not local-only") from exc
        except Exception as exc:  # pragma: no cover - unexpected
            raise RoutingError("OSRM routing failed") from exc
        routes = response.get("routes") if isinstance(response, dict) else None
        if not routes:
            raise RoutingError("OSRM returned no routes", code="NO_ROUTE")
        route = routes[0]
        duration_min = round(float(route.get("duration", 0)) / 60.0, 2)
        distance_m = round(float(route.get("distance", 0)), 2)
        return RouteResult(
            duration_min=duration_min,
            distance_m=distance_m,
            provider=self.provider,
            mode=request.mode,
            metadata={
                "provider_version": self._profile_version,
                "raw": route,
            },
        )
