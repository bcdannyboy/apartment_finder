from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from services.common.enums import EvidenceKind
from services.common.hashes import sha256_text


@dataclass(frozen=True)
class EvidenceIssue:
    code: str
    message: str
    severity: str = "error"
    field_path: Optional[str] = None


class EvidenceLocatorError(ValueError):
    pass


def _select_content(snapshot: Any, source_format: Optional[str]) -> Optional[str]:
    if source_format in (None, "text"):
        return getattr(snapshot, "text", None)
    if source_format == "html":
        return getattr(snapshot, "html", None)
    if source_format == "markdown":
        return getattr(snapshot, "markdown", None)
    return None


def resolve_text_span(snapshot: Any, locator: Dict[str, Any]) -> str:
    content = _select_content(snapshot, locator.get("source_format"))
    if content is None:
        raise EvidenceLocatorError("content unavailable for text_span")
    try:
        start = int(locator["start_char"])
        end = int(locator["end_char"])
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceLocatorError("text_span requires start_char and end_char") from exc
    if start < 0 or end < 0 or start >= end or end > len(content):
        raise EvidenceLocatorError("text_span locator out of bounds")
    return content[start:end]


def validate_evidence_ref(evidence_ref: Any, snapshot: Any, field_path: Optional[str] = None) -> List[EvidenceIssue]:
    issues: List[EvidenceIssue] = []
    snapshot_id = getattr(snapshot, "snapshot_id", None)
    if evidence_ref.snapshot_id != snapshot_id:
        issues.append(
            EvidenceIssue(
                code="snapshot_id_mismatch",
                message="evidence snapshot_id does not match snapshot",
                field_path=field_path,
            )
        )
        return issues

    kind = evidence_ref.kind
    if isinstance(kind, str):
        try:
            kind = EvidenceKind(kind)
        except ValueError:
            issues.append(
                EvidenceIssue(
                    code="unsupported_kind",
                    message="unsupported evidence kind",
                    field_path=field_path,
                )
            )
            return issues

    if kind == EvidenceKind.text_span:
        locator = evidence_ref.locator
        content = _select_content(snapshot, locator.get("source_format"))
        if content is None:
            issues.append(
                EvidenceIssue(
                    code="content_missing",
                    message="text_span source_format not available on snapshot",
                    field_path=field_path,
                )
            )
            return issues
        try:
            start = int(locator["start_char"])
            end = int(locator["end_char"])
        except (KeyError, TypeError, ValueError):
            issues.append(
                EvidenceIssue(
                    code="invalid_locator",
                    message="text_span requires start_char and end_char",
                    field_path=field_path,
                )
            )
            return issues
        if start < 0 or end < 0 or start >= end or end > len(content):
            issues.append(
                EvidenceIssue(
                    code="span_out_of_bounds",
                    message="text_span locator out of bounds",
                    field_path=field_path,
                )
            )
            return issues
        span = content[start:end]
        excerpt = evidence_ref.excerpt
        if excerpt is not None and excerpt != span:
            issues.append(
                EvidenceIssue(
                    code="excerpt_mismatch",
                    message="excerpt does not match resolved span",
                    field_path=field_path,
                )
            )
        text_hash = locator.get("text_hash")
        if text_hash is not None:
            computed = sha256_text(span)
            if computed != text_hash:
                issues.append(
                    EvidenceIssue(
                        code="text_hash_mismatch",
                        message="text_hash does not match resolved span",
                        field_path=field_path,
                    )
                )
    elif kind == EvidenceKind.image_region:
        locator = evidence_ref.locator
        image_ref = locator.get("image_ref")
        images = getattr(snapshot, "images", {}) or {}
        if image_ref not in images:
            issues.append(
                EvidenceIssue(
                    code="image_missing",
                    message="image_ref not found on snapshot",
                    field_path=field_path,
                )
            )
            return issues
        image_meta = images[image_ref]
        try:
            x = int(locator["x"])
            y = int(locator["y"])
            width = int(locator["width"])
            height = int(locator["height"])
        except (KeyError, TypeError, ValueError):
            issues.append(
                EvidenceIssue(
                    code="invalid_locator",
                    message="image_region requires x, y, width, height",
                    field_path=field_path,
                )
            )
            return issues
        if width <= 0 or height <= 0:
            issues.append(
                EvidenceIssue(
                    code="invalid_dimensions",
                    message="image_region width and height must be positive",
                    field_path=field_path,
                )
            )
        if x < 0 or y < 0 or (x + width) > image_meta.width or (y + height) > image_meta.height:
            issues.append(
                EvidenceIssue(
                    code="region_out_of_bounds",
                    message="image_region outside image bounds",
                    field_path=field_path,
                )
            )
    else:
        issues.append(
            EvidenceIssue(
                code="unsupported_kind",
                message="unsupported evidence kind",
                field_path=field_path,
            )
        )
    return issues
