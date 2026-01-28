from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

import pytest

from services.common.enums import CommuteMode, GeoProvider, RoutingProvider
from services.common.local_bind import LocalBindError, ensure_local_url
from services.geo_commute.cache import CommuteCache, CommuteCacheKey, TimeBucketPolicy
from fastapi.testclient import TestClient

from services.geo_commute.compliance import (
    GtfsRedistributionError,
    GtfsStorageError,
    GtfsStoragePolicy,
    OtpGraphManager,
)
from services.geo_commute.models import (
    CommuteRequest,
    GeocodeError,
    GeocodePrecision,
    GeocodeRequest,
    GeocodeResult,
    RouteRequest,
    RouteResult,
    RoutingError,
)
from services.geo_commute.providers import PeliasGeocoder, ValhallaRouter
from services.geo_commute.repository import GeoCommuteRepository
from services.geo_commute.service import (
    GeoCommuteObservability,
    GeoCommuteService,
    Geocoder,
    RoutingEngine,
)


FIXED_TIME = datetime(2026, 1, 28, 8, 17, tzinfo=timezone.utc)


class StubGeocoderProvider:
    def __init__(self, provider: GeoProvider, *, result: GeocodeResult | None = None, error: str | None = None):
        self.provider = provider
        self._result = result
        self._error = error
        self.calls = 0

    def geocode(self, request: GeocodeRequest) -> GeocodeResult | None:
        self.calls += 1
        if self._error:
            raise GeocodeError(self._error)
        return self._result


class StubRouter:
    def __init__(self, provider: RoutingProvider, *, result: RouteResult | None = None, error: str | None = None):
        self.provider = provider
        self._result = result
        self._error = error
        self.calls = 0
        self._version = f"{provider.value}-v1"

    @property
    def version_token(self) -> str:
        return f"{self.provider.value}:{self._version}"

    def set_graph_version(self, version: str) -> None:
        self._version = version

    def route(self, request: RouteRequest) -> RouteResult:
        self.calls += 1
        if self._error:
            raise RoutingError(self._error)
        assert self._result is not None
        return self._result


class CountingTransport:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def request(self, *, method: str, url: str, params=None, json_body=None):
        self.calls += 1
        return self.payload


class StubGeoCommuteService:
    def __init__(self, geocode_result: GeocodeResult, commute_result: RouteResult):
        self._geocode = geocode_result
        self._commute = commute_result

    def geocode_address(self, request: GeocodeRequest) -> GeocodeResult:
        return self._geocode

    def commute(self, request: CommuteRequest):
        from services.geo_commute.models import CommuteResult

        return CommuteResult(cache_key="origin_h3=abc|anchor_id=anchor|mode=walk|time_bucket=2026-01-28T08:00:00+00:00", cache_hit=False, route=self._commute)


class StubOtpManager:
    def __init__(self):
        self.calls = 0

    def register_feed(self, *, path: str, fingerprint: str):
        self.calls += 1

    def ensure_graph(self):
        from services.geo_commute.compliance import OtpGraphBuildResult

        return OtpGraphBuildResult(graph_version="otp-graph-1", fingerprint="fp-1", built_at=FIXED_TIME)


def _route_result(provider: RoutingProvider, mode: CommuteMode) -> RouteResult:
    return RouteResult(
        duration_min=15.5,
        distance_m=4500.0,
        provider=provider,
        mode=mode,
        metadata={"provider_version": f"{provider.value}-v1"},
    )


def test_local_only_url_enforced():
    ensure_local_url("http://localhost:4000")
    ensure_local_url("http://pelias:4000", allowed_hosts={"pelias"})
    with pytest.raises(LocalBindError):
        ensure_local_url("https://api.mapbox.com", allowed_hosts={"pelias"})


def test_geocode_primary_and_fallback_behavior():
    primary_result = GeocodeResult(
        latitude=37.77,
        longitude=-122.41,
        precision=GeocodePrecision.rooftop,
        confidence=0.91,
        provider=GeoProvider.pelias,
        label="Primary",
    )
    fallback_result = GeocodeResult(
        latitude=37.78,
        longitude=-122.42,
        precision=GeocodePrecision.locality,
        confidence=0.55,
        provider=GeoProvider.nominatim,
        label="Fallback",
    )
    primary = StubGeocoderProvider(GeoProvider.pelias, result=primary_result)
    fallback = StubGeocoderProvider(GeoProvider.nominatim, result=fallback_result)
    obs = GeoCommuteObservability()
    geocoder = Geocoder(primary=primary, fallback=fallback, observability=obs)
    result = geocoder.geocode(GeocodeRequest(address="123 Main St"))
    assert result.provider == GeoProvider.pelias
    assert primary.calls == 1
    assert fallback.calls == 0

    primary_empty = StubGeocoderProvider(GeoProvider.pelias, result=None)
    fallback_used = StubGeocoderProvider(GeoProvider.nominatim, result=fallback_result)
    geocoder = Geocoder(primary=primary_empty, fallback=fallback_used, observability=obs)
    result = geocoder.geocode(GeocodeRequest(address="123 Main St"))
    assert result.provider == GeoProvider.nominatim
    assert primary_empty.calls == 1
    assert fallback_used.calls == 1

    primary_error = StubGeocoderProvider(GeoProvider.pelias, error="Pelias down")
    fallback_error = StubGeocoderProvider(GeoProvider.nominatim, error="Nominatim down")
    geocoder = Geocoder(primary=primary_error, fallback=fallback_error, observability=obs)
    with pytest.raises(GeocodeError) as excinfo:
        geocoder.geocode(GeocodeRequest(address="123 Main St"))
    assert excinfo.value.code == "NO_RESULTS"


def test_geocode_precision_and_confidence_fields_are_stable():
    transport = CountingTransport(
        {
            "features": [
                {
                    "geometry": {"coordinates": [-122.401, 37.791]},
                    "properties": {"confidence": 1.2, "layer": "address", "label": "Test"},
                }
            ]
        }
    )
    pelias = PeliasGeocoder(
        base_url="http://pelias:4000",
        transport=transport,
        allowed_hosts={"pelias"},
    )
    first = pelias.geocode(GeocodeRequest(address="1 Market"))
    second = pelias.geocode(GeocodeRequest(address="1 Market"))
    assert first is not None
    assert first.precision == GeocodePrecision.rooftop
    assert 0.0 <= first.confidence <= 1.0
    assert first.latitude == second.latitude
    assert first.longitude == second.longitude
    assert first.confidence == second.confidence


def test_routing_engine_selection_by_mode_and_fallback():
    otp = StubRouter(RoutingProvider.otp, result=_route_result(RoutingProvider.otp, CommuteMode.transit))
    valhalla = StubRouter(RoutingProvider.valhalla, result=_route_result(RoutingProvider.valhalla, CommuteMode.walk))
    osrm = StubRouter(RoutingProvider.osrm, result=_route_result(RoutingProvider.osrm, CommuteMode.walk))
    engine = RoutingEngine(otp=otp, valhalla=valhalla, osrm=osrm)

    transit_request = CommuteRequest(
        origin_latitude=37.77,
        origin_longitude=-122.41,
        destination_latitude=37.78,
        destination_longitude=-122.42,
        mode=CommuteMode.transit,
        depart_at=FIXED_TIME,
        origin_h3="8928308280fffff",
        anchor_id="anchor-1",
    )
    engine.route(transit_request)
    assert otp.calls == 1
    assert valhalla.calls == 0

    walk_request = CommuteRequest(
        origin_latitude=37.77,
        origin_longitude=-122.41,
        destination_latitude=37.78,
        destination_longitude=-122.42,
        mode=CommuteMode.walk,
        depart_at=FIXED_TIME,
        origin_h3="8928308280fffff",
        anchor_id="anchor-1",
    )
    engine.route(walk_request)
    assert valhalla.calls == 1

    valhalla_error = StubRouter(RoutingProvider.valhalla, error="tiles missing", result=_route_result(RoutingProvider.valhalla, CommuteMode.walk))
    osrm_fallback = StubRouter(RoutingProvider.osrm, result=_route_result(RoutingProvider.osrm, CommuteMode.walk))
    engine = RoutingEngine(otp=otp, valhalla=valhalla_error, osrm=osrm_fallback)
    engine.route(walk_request)
    assert valhalla_error.calls == 1
    assert osrm_fallback.calls == 1


def test_commute_cache_key_shape_and_order():
    policy = TimeBucketPolicy(bucket_minutes=30)
    bucket = policy.bucket_for(FIXED_TIME)
    key = CommuteCacheKey.from_inputs(
        origin_h3=" 8928308280FFFFF ",
        anchor_id=" Anchor-1 ",
        mode=CommuteMode.transit,
        time_bucket=bucket,
    )
    key_str = key.to_key()
    parsed = CommuteCacheKey.parse(key_str)
    assert parsed == key
    assert [segment.split("=")[0] for segment in key_str.split("|")] == [
        "origin_h3",
        "anchor_id",
        "mode",
        "time_bucket",
    ]
    assert "address" not in key_str
    assert "lat" not in key_str
    assert "lon" not in key_str


def test_commute_cache_determinism_and_cache_usage():
    otp = StubRouter(RoutingProvider.otp, result=_route_result(RoutingProvider.otp, CommuteMode.transit))
    valhalla = StubRouter(RoutingProvider.valhalla, result=_route_result(RoutingProvider.valhalla, CommuteMode.walk))
    engine = RoutingEngine(otp=otp, valhalla=valhalla)
    obs = GeoCommuteObservability()
    service = GeoCommuteService(
        geocoder=Geocoder(primary=StubGeocoderProvider(GeoProvider.pelias, result=GeocodeResult(
            latitude=37.77,
            longitude=-122.41,
            precision=GeocodePrecision.rooftop,
            confidence=0.9,
            provider=GeoProvider.pelias,
        ))),
        router=engine,
        cache=CommuteCache(),
        time_bucket_policy=TimeBucketPolicy(bucket_minutes=30),
        observability=obs,
    )
    request = CommuteRequest(
        origin_latitude=37.77,
        origin_longitude=-122.41,
        destination_latitude=37.78,
        destination_longitude=-122.42,
        mode=CommuteMode.walk,
        depart_at=FIXED_TIME,
        origin_h3="8928308280fffff",
        anchor_id="anchor-1",
    )
    first = service.commute(request)
    second = service.commute(request)
    assert first.route.duration_min == second.route.duration_min
    assert first.cache_hit is False
    assert second.cache_hit is True

    changed_origin = CommuteRequest(
        origin_latitude=37.77,
        origin_longitude=-122.41,
        destination_latitude=37.78,
        destination_longitude=-122.42,
        mode=CommuteMode.walk,
        depart_at=FIXED_TIME,
        origin_h3="8928308280aaa",
        anchor_id="anchor-1",
    )
    miss = service.commute(changed_origin)
    assert miss.cache_hit is False


def test_gtfs_storage_policy_local_only_and_no_redistribution(tmp_path):
    feed_path = tmp_path / "feed.zip"
    feed_path.write_text("test")
    os.chmod(feed_path, 0o600)
    policy = GtfsStoragePolicy(allowed_roots=[str(tmp_path)])
    record = policy.register_feed(path=str(feed_path), fingerprint="fp-1")
    assert record.fingerprint == "fp-1"

    with tempfile.TemporaryDirectory() as other_dir:
        other_path = os.path.join(other_dir, "feed.zip")
        with open(other_path, "w", encoding="utf-8") as handle:
            handle.write("test")
        os.chmod(other_path, 0o600)
        with pytest.raises(GtfsStorageError):
            policy.register_feed(path=other_path, fingerprint="fp-2")

    with pytest.raises(GtfsRedistributionError):
        policy.ensure_export_allowed("/tmp/gtfs-export")


def test_gtfs_permissions_are_restricted(tmp_path):
    feed_path = tmp_path / "feed.zip"
    feed_path.write_text("test")
    os.chmod(feed_path, 0o644)
    policy = GtfsStoragePolicy(allowed_roots=[str(tmp_path)])
    with pytest.raises(GtfsStorageError):
        policy.register_feed(path=str(feed_path), fingerprint="fp-3")


def test_gtfs_fingerprint_change_triggers_otp_rebuild():
    with tempfile.TemporaryDirectory() as root:
        feed_path = os.path.join(root, "feed.zip")
        with open(feed_path, "w", encoding="utf-8") as handle:
            handle.write("test")
        os.chmod(feed_path, 0o600)
        policy = GtfsStoragePolicy(allowed_roots=[root])
        manager = OtpGraphManager(storage_policy=policy)
        manager.register_feed(path=feed_path, fingerprint="fp-1")
        first = manager.ensure_graph()
        second = manager.ensure_graph()
        assert first.graph_version == second.graph_version

        manager.register_feed(path=feed_path, fingerprint="fp-2")
        third = manager.ensure_graph()
        assert third.graph_version != first.graph_version


def test_valhalla_tiles_missing_and_profile_version_invalidation():
    missing = ValhallaRouter(
        base_url="http://valhalla:8002",
        transport=CountingTransport({}),
        allowed_hosts={"valhalla"},
        tiles_available=False,
    )
    with pytest.raises(RoutingError):
        missing.route(
            RouteRequest(
                origin_latitude=37.77,
                origin_longitude=-122.41,
                destination_latitude=37.78,
                destination_longitude=-122.42,
                mode=CommuteMode.walk,
                depart_at=FIXED_TIME,
            )
        )

    transport = CountingTransport({"trip": {"summary": {"time": 900, "length": 4.2}}})
    valhalla = ValhallaRouter(
        base_url="http://valhalla:8002",
        transport=transport,
        allowed_hosts={"valhalla"},
        profile_version="v1",
        tiles_version="tiles-v1",
    )
    otp = StubRouter(RoutingProvider.otp, result=_route_result(RoutingProvider.otp, CommuteMode.transit))
    engine = RoutingEngine(otp=otp, valhalla=valhalla)
    service = GeoCommuteService(
        geocoder=Geocoder(primary=StubGeocoderProvider(GeoProvider.pelias, result=GeocodeResult(
            latitude=37.77,
            longitude=-122.41,
            precision=GeocodePrecision.rooftop,
            confidence=0.9,
            provider=GeoProvider.pelias,
        ))),
        router=engine,
        cache=CommuteCache(),
        time_bucket_policy=TimeBucketPolicy(bucket_minutes=30),
    )
    request = CommuteRequest(
        origin_latitude=37.77,
        origin_longitude=-122.41,
        destination_latitude=37.78,
        destination_longitude=-122.42,
        mode=CommuteMode.walk,
        depart_at=FIXED_TIME,
        origin_h3="8928308280fffff",
        anchor_id="anchor-1",
    )
    service.commute(request)
    assert transport.calls == 1
    valhalla.set_profile_version("v2")
    service.commute(request)
    assert transport.calls == 2


def test_observability_includes_fallback_and_cache_events():
    obs = GeoCommuteObservability()
    primary = StubGeocoderProvider(GeoProvider.pelias, result=None)
    fallback = StubGeocoderProvider(
        GeoProvider.nominatim,
        result=GeocodeResult(
            latitude=37.77,
            longitude=-122.41,
            precision=GeocodePrecision.locality,
            confidence=0.5,
            provider=GeoProvider.nominatim,
        ),
    )
    geocoder = Geocoder(primary=primary, fallback=fallback, observability=obs)
    otp = StubRouter(RoutingProvider.otp, result=_route_result(RoutingProvider.otp, CommuteMode.transit))
    valhalla = StubRouter(RoutingProvider.valhalla, result=_route_result(RoutingProvider.valhalla, CommuteMode.walk))
    engine = RoutingEngine(otp=otp, valhalla=valhalla, observability=obs)
    service = GeoCommuteService(
        geocoder=geocoder,
        router=engine,
        cache=CommuteCache(),
        time_bucket_policy=TimeBucketPolicy(bucket_minutes=30),
        observability=obs,
    )
    geocoder.geocode(GeocodeRequest(address="1 Market"))
    request = CommuteRequest(
        origin_latitude=37.77,
        origin_longitude=-122.41,
        destination_latitude=37.78,
        destination_longitude=-122.42,
        mode=CommuteMode.walk,
        depart_at=FIXED_TIME,
        origin_h3="8928308280fffff",
        anchor_id="anchor-1",
    )
    service.commute(request)
    service.commute(request)

    events = obs.events()
    assert any(event.event_type == "geocode" and event.details.get("fallback_used") for event in events)
    assert any(event.event_type == "cache_miss" for event in events)
    assert any(event.event_type == "cache_hit" for event in events)


def test_geo_commute_api_contracts(monkeypatch):
    import services.geo_commute.app as geo_app

    geocode_result = GeocodeResult(
        latitude=37.77,
        longitude=-122.41,
        precision=GeocodePrecision.rooftop,
        confidence=0.9,
        provider=GeoProvider.pelias,
    )
    commute_result = RouteResult(
        duration_min=10.0,
        distance_m=2000.0,
        provider=RoutingProvider.valhalla,
        mode=CommuteMode.walk,
        metadata={"provider_version": "valhalla-v1"},
    )
    geo_app._service = StubGeoCommuteService(geocode_result, commute_result)
    geo_app._otp_manager = StubOtpManager()
    geo_app._repository = GeoCommuteRepository()

    client = TestClient(geo_app.app)
    response = client.post(
        "/geo/geocode",
        json={"schema_version": "v1", "address": "1 Market"},
    )
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["data"]["provider"] == "pelias"

    commute = client.post(
        "/geo/commute",
        json={
            "schema_version": "v1",
            "origin_latitude": 37.77,
            "origin_longitude": -122.41,
            "destination_latitude": 37.78,
            "destination_longitude": -122.42,
            "mode": "walk",
            "depart_at": FIXED_TIME.isoformat(),
            "origin_h3": "8928308280fffff",
            "anchor_id": "anchor-1",
        },
    )
    commute_payload = commute.json()
    assert commute_payload["status"] == "ok"
    assert commute_payload["data"]["route"]["provider"] == "valhalla"

    gtfs = client.post(
        "/geo/gtfs/register",
        json={"schema_version": "v1", "path": "/tmp/gtfs/feed.zip", "fingerprint": "fp-1"},
    )
    gtfs_payload = gtfs.json()
    assert gtfs_payload["status"] == "ok"
    assert gtfs_payload["data"]["graph_version"] == "otp-graph-1"
