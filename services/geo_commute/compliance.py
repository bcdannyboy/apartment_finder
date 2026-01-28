from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, Optional

from services.geo_commute.models import GeoCommuteError


class GtfsStorageError(GeoCommuteError):
    def __init__(self, message: str, *, details: Optional[Dict[str, str]] = None) -> None:
        super().__init__(message, code="GTFS_STORAGE_ERROR", details=details)


class GtfsRedistributionError(GeoCommuteError):
    def __init__(self, message: str, *, details: Optional[Dict[str, str]] = None) -> None:
        super().__init__(message, code="GTFS_REDISTRIBUTION_BLOCKED", details=details)


class OtpGraphBuildError(GeoCommuteError):
    def __init__(self, message: str, *, details: Optional[Dict[str, str]] = None) -> None:
        super().__init__(message, code="OTP_GRAPH_BUILD_ERROR", details=details)


@dataclass(frozen=True)
class GtfsFeedRecord:
    path: str
    fingerprint: str
    registered_at: datetime


@dataclass(frozen=True)
class OtpGraphBuildResult:
    graph_version: str
    fingerprint: str
    built_at: datetime


def _real_path(path: str) -> str:
    return os.path.realpath(path)


def _is_allowed_path(path: str, allowed_roots: Iterable[str]) -> bool:
    real_path = _real_path(path)
    for root in allowed_roots:
        root_path = _real_path(root)
        try:
            common = os.path.commonpath([real_path, root_path])
        except ValueError:
            continue
        if common == root_path:
            return True
    return False


def _validate_permissions(path: str) -> None:
    mode = stat.S_IMODE(os.stat(path).st_mode)
    # Allow owner rwx and group read-only; forbid group write/exec and any other access.
    if mode & 0o037:
        raise GtfsStorageError(
            "GTFS file permissions must be restricted",
            details={"path": path, "mode": oct(mode)},
        )


class GtfsStoragePolicy:
    def __init__(self, *, allowed_roots: Iterable[str]) -> None:
        self._allowed_roots = list(allowed_roots)
        if not self._allowed_roots:
            raise ValueError("allowed_roots must be provided")
        self._feeds: Dict[str, GtfsFeedRecord] = {}

    def register_feed(self, *, path: str, fingerprint: str) -> GtfsFeedRecord:
        if not os.path.exists(path):
            raise GtfsStorageError("GTFS feed path does not exist", details={"path": path})
        if not _is_allowed_path(path, self._allowed_roots):
            raise GtfsStorageError(
                "GTFS feed path must be local-only",
                details={"path": path},
            )
        _validate_permissions(path)
        record = GtfsFeedRecord(
            path=_real_path(path),
            fingerprint=fingerprint,
            registered_at=datetime.now(tz=timezone.utc),
        )
        self._feeds[fingerprint] = record
        return record

    def feed_for(self, fingerprint: str) -> Optional[GtfsFeedRecord]:
        return self._feeds.get(fingerprint)

    def ensure_export_allowed(self, target_path: str) -> None:
        if not _is_allowed_path(target_path, self._allowed_roots):
            raise GtfsRedistributionError(
                "GTFS redistribution blocked; target must be approved local storage",
                details={"path": target_path},
            )


class OtpGraphManager:
    def __init__(
        self,
        *,
        storage_policy: GtfsStoragePolicy,
        builder: Optional[Callable[[str], str]] = None,
    ) -> None:
        self._storage_policy = storage_policy
        self._builder = builder
        self._active_fingerprint: Optional[str] = None
        self._graph_version: Optional[str] = None
        self._build_counter = 0
        self._graph_version_fingerprint: Optional[str] = None
        self._last_built_at: datetime = datetime.fromtimestamp(0, tz=timezone.utc)

    @property
    def graph_version(self) -> Optional[str]:
        return self._graph_version

    @property
    def active_fingerprint(self) -> Optional[str]:
        return self._active_fingerprint

    def register_feed(self, *, path: str, fingerprint: str) -> GtfsFeedRecord:
        record = self._storage_policy.register_feed(path=path, fingerprint=fingerprint)
        self._active_fingerprint = fingerprint
        return record

    def ensure_graph(self) -> OtpGraphBuildResult:
        if not self._active_fingerprint:
            raise OtpGraphBuildError("No GTFS fingerprint registered")
        if self._graph_version is None or self._graph_version_fingerprint != self._active_fingerprint:
            return self._rebuild_graph(self._active_fingerprint)
        return OtpGraphBuildResult(
            graph_version=self._graph_version,
            fingerprint=self._active_fingerprint,
            built_at=self._last_built_at,
        )

    def _rebuild_graph(self, fingerprint: str) -> OtpGraphBuildResult:
        try:
            version = self._builder(fingerprint) if self._builder else None
        except Exception as exc:  # pragma: no cover - unexpected builder errors
            raise OtpGraphBuildError("OTP graph build failed") from exc
        if version is None:
            self._build_counter += 1
            version = f"otp-graph-{self._build_counter}"
        self._graph_version = version
        self._graph_version_fingerprint = fingerprint
        self._last_built_at = datetime.now(tz=timezone.utc)
        return OtpGraphBuildResult(
            graph_version=self._graph_version,
            fingerprint=fingerprint,
            built_at=self._last_built_at,
        )
