from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.common.enums import EvidenceKind


@dataclass(frozen=True)
class ImageMeta:
    image_ref: str
    width: int
    height: int


@dataclass(frozen=True)
class SnapshotContent:
    snapshot_id: str
    source_id: str
    html: Optional[str] = None
    text: Optional[str] = None
    markdown: Optional[str] = None
    images: Dict[str, ImageMeta] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceRef:
    snapshot_id: str
    kind: EvidenceKind
    locator: Dict[str, Any]
    excerpt: Optional[str] = None


@dataclass(frozen=True)
class FieldCandidate:
    field_path: str
    value: Any
    confidence: Optional[float]
    evidence: List[EvidenceRef]
    extractor: str


@dataclass(frozen=True)
class SourceObservationRecord:
    observation_id: str
    snapshot_id: str
    source_id: str
    extracted_json: Optional[Dict[str, Any]]
    extractor_version: str
    validation_report: Dict[str, Any]
    created_at: datetime


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)
