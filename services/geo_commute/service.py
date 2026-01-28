from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from services.common.enums import CommuteMode, GeoProvider, RoutingProvider
from services.geo_commute.cache import CommuteCache, CommuteCacheKey, TimeBucketPolicy
from services.geo_commute.compliance import OtpGraphManager
from services.geo_commute.models import (
    CommuteRequest,
    CommuteResult,
    GeocodeError,
    GeocodeRequest,
    GeocodeResult,
    RouteResult,
    RoutingError,
)
from services.geo_commute.providers import NominatimGeocoder, OsrmRouter, OtpRouter, PeliasGeocoder, ValhallaRouter


@dataclass(frozen=True)
class CommuteEvent:
    event_type: str
    details: Dict[str, Any]
    recorded_at: datetime


class GeoCommuteObservability:
    def __init__(self) -> None:
        self._events: list[CommuteEvent] = []

    def record(self, event_type: str, **details: Any) -> None:
        self._events.append(
            CommuteEvent(
                event_type=event_type,
                details=details,
                recorded_at=datetime.now(tz=timezone.utc),
            )
        )

    def events(self) -> list[CommuteEvent]:
        return list(self._events)


class Geocoder:
    def __init__(
        self,
        *,
        primary: PeliasGeocoder,
        fallback: Optional[NominatimGeocoder] = None,
        observability: Optional[GeoCommuteObservability] = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._observability = observability

    def geocode(self, request: GeocodeRequest) -> GeocodeResult:
        fallback_reason: Optional[str] = None
        try:
            result = self._primary.geocode(request)
        except GeocodeError as exc:
            fallback_reason = str(exc)
            result = None
        if result:
            self._record_geocode(result, fallback_used=False, fallback_reason=None)
            return result
        if not self._fallback:
            raise GeocodeError("Geocode failed", code="NO_RESULTS")
        try:
            fallback_result = self._fallback.geocode(request)
        except GeocodeError as exc:
            raise GeocodeError(
                "Geocode failed",
                code="NO_RESULTS",
                details={"primary_error": fallback_reason or "no_results", "fallback_error": str(exc)},
            ) from exc
        if not fallback_result:
            raise GeocodeError(
                "Geocode failed",
                code="NO_RESULTS",
                details={"primary_error": fallback_reason or "no_results", "fallback_error": "no_results"},
            )
        self._record_geocode(
            fallback_result,
            fallback_used=True,
            fallback_reason=fallback_reason or "no_results",
        )
        return fallback_result

    def _record_geocode(self, result: GeocodeResult, *, fallback_used: bool, fallback_reason: Optional[str]) -> None:
        if not self._observability:
            return
        self._observability.record(
            "geocode",
            provider=result.provider.value,
            precision=result.precision.value,
            confidence=result.confidence,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )


class RoutingEngine:
    def __init__(
        self,
        *,
        otp: OtpRouter,
        valhalla: ValhallaRouter,
        osrm: Optional[OsrmRouter] = None,
        otp_graph_manager: Optional[OtpGraphManager] = None,
        observability: Optional[GeoCommuteObservability] = None,
    ) -> None:
        self._otp = otp
        self._valhalla = valhalla
        self._osrm = osrm
        self._otp_graph_manager = otp_graph_manager
        self._observability = observability

    def prepare(self, request: CommuteRequest) -> Tuple[str, Optional[str]]:
        fingerprint = None
        if request.mode == CommuteMode.transit and self._otp_graph_manager:
            build = self._otp_graph_manager.ensure_graph()
            self._otp.set_graph_version(build.graph_version)
            fingerprint = build.fingerprint
        return self.version_token(request.mode), fingerprint

    def version_token(self, mode: CommuteMode) -> str:
        if mode == CommuteMode.transit:
            return self._otp.version_token
        if mode in (CommuteMode.walk, CommuteMode.bike, CommuteMode.drive):
            return self._valhalla.version_token
        return "unknown"

    def route(self, request: CommuteRequest) -> RouteResult:
        if request.mode == CommuteMode.transit:
            result = self._otp.route(request)
            self._record_route(result)
            return result
        try:
            result = self._valhalla.route(request)
            self._record_route(result)
            return result
        except RoutingError as exc:
            if self._osrm is None:
                raise
            fallback = self._osrm.route(request)
            self._record_route(
                fallback,
                fallback_reason=str(exc),
                primary_provider=RoutingProvider.valhalla.value,
            )
            return fallback

    def _record_route(
        self,
        result: RouteResult,
        *,
        fallback_reason: Optional[str] = None,
        primary_provider: Optional[str] = None,
    ) -> None:
        if not self._observability:
            return
        self._observability.record(
            "route",
            provider=result.provider.value,
            mode=result.mode.value,
            provider_version=result.metadata.get("provider_version"),
            fallback_reason=fallback_reason,
            primary_provider=primary_provider,
        )


class GeoCommuteService:
    def __init__(
        self,
        *,
        geocoder: Geocoder,
        router: RoutingEngine,
        cache: Optional[CommuteCache] = None,
        time_bucket_policy: Optional[TimeBucketPolicy] = None,
        observability: Optional[GeoCommuteObservability] = None,
    ) -> None:
        self._geocoder = geocoder
        self._router = router
        self._cache = cache or CommuteCache()
        self._time_bucket_policy = time_bucket_policy or TimeBucketPolicy()
        self._observability = observability or GeoCommuteObservability()

    @property
    def observability(self) -> GeoCommuteObservability:
        return self._observability

    def geocode_address(self, request: GeocodeRequest) -> GeocodeResult:
        return self._geocoder.geocode(request)

    def commute(self, request: CommuteRequest) -> CommuteResult:
        time_bucket = self._time_bucket_policy.bucket_for(request.depart_at)
        cache_key = CommuteCacheKey.from_inputs(
            origin_h3=request.origin_h3,
            anchor_id=request.anchor_id,
            mode=request.mode,
            time_bucket=time_bucket,
        ).to_key()
        version_token, fingerprint = self._router.prepare(request)
        if request.gtfs_fingerprint and fingerprint and request.gtfs_fingerprint != fingerprint:
            raise RoutingError(
                "GTFS fingerprint mismatch",
                code="GTFS_FINGERPRINT_MISMATCH",
                details={"expected": fingerprint, "received": request.gtfs_fingerprint},
            )
        cached = self._cache.get(cache_key, version_token=version_token)
        if cached:
            self._record_cache_event(cache_key, cached, cache_hit=True, fingerprint=fingerprint)
            return CommuteResult(cache_key=cache_key, cache_hit=True, route=cached)
        result = self._router.route(request)
        self._cache.set(cache_key, route=result, version_token=version_token)
        self._record_cache_event(cache_key, result, cache_hit=False, fingerprint=fingerprint)
        return CommuteResult(cache_key=cache_key, cache_hit=False, route=result)

    def _record_cache_event(
        self,
        cache_key: str,
        route: RouteResult,
        *,
        cache_hit: bool,
        fingerprint: Optional[str],
    ) -> None:
        self._observability.record(
            "cache_hit" if cache_hit else "cache_miss",
            cache_key=cache_key,
            provider=route.provider.value,
            mode=route.mode.value,
            provider_version=route.metadata.get("provider_version"),
            feed_fingerprint=fingerprint,
        )
