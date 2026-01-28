from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, List, Optional, Set
from urllib.parse import urlparse

from services.geo_commute.cache import CommuteCache, TimeBucketPolicy
from services.geo_commute.compliance import GtfsStoragePolicy, OtpGraphManager
from services.geo_commute.providers import (
    LocalHttpTransport,
    NominatimGeocoder,
    OsrmRouter,
    OtpRouter,
    PeliasGeocoder,
    ValhallaRouter,
)
from services.geo_commute.repository import GeoCommuteRepository
from services.geo_commute.service import GeoCommuteObservability, GeoCommuteService, Geocoder, RoutingEngine


@dataclass(frozen=True)
class GeoCommuteConfig:
    pelias_url: str = "http://127.0.0.1:4000"
    nominatim_url: str = "http://127.0.0.1:8080"
    otp_url: str = "http://127.0.0.1:8080"
    valhalla_url: str = "http://127.0.0.1:8002"
    osrm_url: str = "http://127.0.0.1:5000"
    allow_osrm_fallback: bool = True
    time_bucket_minutes: int = 30
    gtfs_allowed_roots: Optional[List[str]] = None


def _hosts_from_urls(urls: Iterable[str]) -> Set[str]:
    hosts: Set[str] = set()
    for url in urls:
        parsed = urlparse(url)
        if parsed.hostname:
            hosts.add(parsed.hostname)
    return hosts


def load_geo_commute_config() -> GeoCommuteConfig:
    roots = os.getenv("GTFS_ALLOWED_ROOTS")
    gtfs_roots = [root.strip() for root in roots.split(",") if root.strip()] if roots else None
    return GeoCommuteConfig(
        pelias_url=os.getenv("PELIAS_URL", GeoCommuteConfig.pelias_url),
        nominatim_url=os.getenv("NOMINATIM_URL", GeoCommuteConfig.nominatim_url),
        otp_url=os.getenv("OTP_URL", GeoCommuteConfig.otp_url),
        valhalla_url=os.getenv("VALHALLA_URL", GeoCommuteConfig.valhalla_url),
        osrm_url=os.getenv("OSRM_URL", GeoCommuteConfig.osrm_url),
        allow_osrm_fallback=os.getenv("ALLOW_OSRM_FALLBACK", "true").lower() == "true",
        time_bucket_minutes=int(os.getenv("COMMUTE_BUCKET_MINUTES", "30")),
        gtfs_allowed_roots=gtfs_roots,
    )


def build_geo_commute_service(
    *,
    config: Optional[GeoCommuteConfig] = None,
    repository: Optional[GeoCommuteRepository] = None,
) -> tuple[GeoCommuteService, OtpGraphManager | None, GeoCommuteRepository]:
    cfg = config or load_geo_commute_config()
    urls = [cfg.pelias_url, cfg.nominatim_url, cfg.otp_url, cfg.valhalla_url, cfg.osrm_url]
    allowed_hosts = _hosts_from_urls(urls)
    transport = LocalHttpTransport(allowed_hosts=allowed_hosts)

    pelias = PeliasGeocoder(base_url=cfg.pelias_url, transport=transport, allowed_hosts=allowed_hosts)
    nominatim = NominatimGeocoder(base_url=cfg.nominatim_url, transport=transport, allowed_hosts=allowed_hosts)
    otp = OtpRouter(base_url=cfg.otp_url, transport=transport, allowed_hosts=allowed_hosts)
    valhalla = ValhallaRouter(base_url=cfg.valhalla_url, transport=transport, allowed_hosts=allowed_hosts)
    osrm = None
    if cfg.allow_osrm_fallback:
        osrm = OsrmRouter(base_url=cfg.osrm_url, transport=transport, allowed_hosts=allowed_hosts)

    storage_policy = None
    otp_manager = None
    if cfg.gtfs_allowed_roots:
        storage_policy = GtfsStoragePolicy(allowed_roots=cfg.gtfs_allowed_roots)
        otp_manager = OtpGraphManager(storage_policy=storage_policy)

    observability = GeoCommuteObservability()
    geocoder = Geocoder(primary=pelias, fallback=nominatim, observability=observability)
    router = RoutingEngine(otp=otp, valhalla=valhalla, osrm=osrm, otp_graph_manager=otp_manager, observability=observability)
    service = GeoCommuteService(
        geocoder=geocoder,
        router=router,
        cache=CommuteCache(),
        time_bucket_policy=TimeBucketPolicy(bucket_minutes=cfg.time_bucket_minutes),
        observability=observability,
    )
    repo = repository or GeoCommuteRepository()
    return service, otp_manager, repo
