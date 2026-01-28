from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from services.common.enums import CommuteMode
from services.geo_commute.models import RouteResult, ensure_timezone


@dataclass(frozen=True)
class CommuteCacheKey:
    origin_h3: str
    anchor_id: str
    mode: CommuteMode
    time_bucket: str

    def to_key(self) -> str:
        return (
            f"origin_h3={self.origin_h3}|"
            f"anchor_id={self.anchor_id}|"
            f"mode={self.mode.value}|"
            f"time_bucket={self.time_bucket}"
        )

    @classmethod
    def parse(cls, value: str) -> "CommuteCacheKey":
        parts = value.split("|")
        expected = ("origin_h3", "anchor_id", "mode", "time_bucket")
        if len(parts) != len(expected):
            raise ValueError("Commute cache key must include 4 fields")
        extracted: Dict[str, str] = {}
        for part, field in zip(parts, expected):
            if not part.startswith(f"{field}="):
                raise ValueError("Commute cache key order is invalid")
            extracted[field] = part[len(field) + 1 :]
        return cls(
            origin_h3=extracted["origin_h3"],
            anchor_id=extracted["anchor_id"],
            mode=CommuteMode(extracted["mode"]),
            time_bucket=extracted["time_bucket"],
        )

    @classmethod
    def from_inputs(
        cls,
        *,
        origin_h3: str,
        anchor_id: str,
        mode: CommuteMode,
        time_bucket: str,
    ) -> "CommuteCacheKey":
        return cls(
            origin_h3=_normalize_identifier(origin_h3),
            anchor_id=_normalize_identifier(anchor_id),
            mode=mode,
            time_bucket=time_bucket,
        )


@dataclass(frozen=True)
class CommuteCacheEntry:
    route: RouteResult
    version_token: str
    created_at: datetime


def _normalize_identifier(value: str) -> str:
    return " ".join(value.strip().lower().split())


@dataclass(frozen=True)
class TimeBucketPolicy:
    bucket_minutes: int = 30

    def __post_init__(self) -> None:
        if self.bucket_minutes <= 0:
            raise ValueError("bucket_minutes must be positive")

    def bucket_for(self, dt: datetime) -> str:
        dt = ensure_timezone(dt)
        minutes = dt.hour * 60 + dt.minute
        bucket_minutes = (minutes // self.bucket_minutes) * self.bucket_minutes
        bucket_hour = bucket_minutes // 60
        bucket_minute = bucket_minutes % 60
        bucket_dt = dt.replace(hour=bucket_hour, minute=bucket_minute, second=0, microsecond=0)
        return bucket_dt.isoformat()


class CommuteCache:
    def __init__(self) -> None:
        self._entries: Dict[str, CommuteCacheEntry] = {}

    def get(self, key: str, *, version_token: str) -> Optional[RouteResult]:
        entry = self._entries.get(key)
        if not entry:
            return None
        if entry.version_token != version_token:
            return None
        return entry.route

    def set(self, key: str, *, route: RouteResult, version_token: str) -> None:
        self._entries[key] = CommuteCacheEntry(
            route=route,
            version_token=version_token,
            created_at=datetime.now(tz=timezone.utc),
        )

    def entries(self) -> Dict[str, CommuteCacheEntry]:
        return dict(self._entries)
