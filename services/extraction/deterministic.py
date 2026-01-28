from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from services.common.enums import EvidenceKind
from services.common.hashes import sha256_text
from services.extraction.models import EvidenceRef, FieldCandidate, SnapshotContent


_JSONLD_RE = re.compile(
    r"<script[^>]*type=\"application/ld\+json\"[^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)

_PRICE_RE = re.compile(r"\$[0-9][0-9,]*(?:\s*/\s*mo|\s*per\s*month)?", re.IGNORECASE)
_BEDS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:bed|beds|br|bd)\b", re.IGNORECASE)
_BATHS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:bath|baths|ba)\b", re.IGNORECASE)
_ADDRESS_RE = re.compile(
    r"\b\d+\s+(?:\d+\/\d+\s+)?[A-Za-z0-9 .]+?\s"
    r"(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road)\b(?:,?\s*[A-Za-z ]+)?",
    re.IGNORECASE,
)
_AVAIL_RE = re.compile(r"\bAvailable(?:\s+Now)?\b", re.IGNORECASE)


@dataclass(frozen=True)
class JsonLdBlock:
    content: str
    start: int
    end: int


def _iter_jsonld_blocks(html: str) -> List[JsonLdBlock]:
    blocks: List[JsonLdBlock] = []
    for match in _JSONLD_RE.finditer(html):
        content = match.group(1)
        blocks.append(JsonLdBlock(content=content, start=match.start(1), end=match.end(1)))
    return blocks


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _extract_address(address: Any) -> Optional[str]:
    if isinstance(address, str):
        return address.strip()
    if isinstance(address, dict):
        parts = []
        for key in ("streetAddress", "addressLocality", "addressRegion", "postalCode"):
            if address.get(key):
                parts.append(str(address[key]).strip())
        return ", ".join(parts) if parts else None
    return None


def _value_span(block: JsonLdBlock, value: str) -> Tuple[int, int]:
    idx = block.content.find(value)
    if idx == -1:
        return block.start, block.end
    start = block.start + idx
    end = start + len(value)
    return start, end


def _evidence_for_span(
    snapshot_id: str, start: int, end: int, source_format: str, content: str
) -> EvidenceRef:
    span = content[start:end]
    return EvidenceRef(
        snapshot_id=snapshot_id,
        kind=EvidenceKind.text_span,
        locator={
            "snapshot_id": snapshot_id,
            "start_char": start,
            "end_char": end,
            "source_format": source_format,
            "text_hash": sha256_text(span),
        },
        excerpt=span,
    )


def _jsonld_candidates(snapshot: SnapshotContent) -> List[FieldCandidate]:
    if not snapshot.html:
        return []
    candidates: List[FieldCandidate] = []
    blocks = _iter_jsonld_blocks(snapshot.html)
    for block in blocks:
        try:
            parsed = json.loads(block.content)
        except json.JSONDecodeError:
            continue
        for item in _as_list(parsed):
            if not isinstance(item, dict):
                continue
            address = _extract_address(item.get("address"))
            if address:
                start, end = _value_span(block, address)
                evidence = _evidence_for_span(snapshot.snapshot_id, start, end, "html", snapshot.html)
                candidates.append(
                    FieldCandidate(
                        field_path="/listing/address",
                        value=address,
                        confidence=0.95,
                        evidence=[evidence],
                        extractor="deterministic-jsonld",
                    )
                )
            offers = item.get("offers")
            for offer in _as_list(offers):
                if not isinstance(offer, dict):
                    continue
                price = offer.get("price")
                if price is not None:
                    price_str = str(price)
                    start, end = _value_span(block, price_str)
                    evidence = _evidence_for_span(
                        snapshot.snapshot_id, start, end, "html", snapshot.html
                    )
                    candidates.append(
                        FieldCandidate(
                            field_path="/listing/price",
                            value=price_str,
                            confidence=0.95,
                            evidence=[evidence],
                            extractor="deterministic-jsonld",
                        )
                    )
                availability = offer.get("availability")
                if availability is not None:
                    avail_str = str(availability).split("/")[-1]
                    start, end = _value_span(block, str(availability))
                    evidence = _evidence_for_span(
                        snapshot.snapshot_id, start, end, "html", snapshot.html
                    )
                    candidates.append(
                        FieldCandidate(
                            field_path="/listing/availability",
                            value=avail_str,
                            confidence=0.9,
                            evidence=[evidence],
                            extractor="deterministic-jsonld",
                        )
                    )
            beds = item.get("numberOfBedrooms")
            if beds is not None:
                beds_str = str(beds)
                start, end = _value_span(block, beds_str)
                evidence = _evidence_for_span(snapshot.snapshot_id, start, end, "html", snapshot.html)
                candidates.append(
                    FieldCandidate(
                        field_path="/listing/beds",
                        value=beds_str,
                        confidence=0.9,
                        evidence=[evidence],
                        extractor="deterministic-jsonld",
                    )
                )
            baths = item.get("numberOfBathroomsTotal")
            if baths is not None:
                baths_str = str(baths)
                start, end = _value_span(block, baths_str)
                evidence = _evidence_for_span(snapshot.snapshot_id, start, end, "html", snapshot.html)
                candidates.append(
                    FieldCandidate(
                        field_path="/listing/baths",
                        value=baths_str,
                        confidence=0.9,
                        evidence=[evidence],
                        extractor="deterministic-jsonld",
                    )
                )
    return candidates


def _regex_candidates(snapshot: SnapshotContent) -> List[FieldCandidate]:
    text = snapshot.text or ""
    candidates: List[FieldCandidate] = []
    for match in _PRICE_RE.finditer(text):
        start, end = match.span()
        evidence = _evidence_for_span(snapshot.snapshot_id, start, end, "text", text)
        candidates.append(
            FieldCandidate(
                field_path="/listing/price",
                value=match.group(0),
                confidence=0.8,
                evidence=[evidence],
                extractor="deterministic-regex",
            )
        )
    for match in _BEDS_RE.finditer(text):
        start, end = match.span(1)
        evidence = _evidence_for_span(snapshot.snapshot_id, start, end, "text", text)
        candidates.append(
            FieldCandidate(
                field_path="/listing/beds",
                value=match.group(1),
                confidence=0.8,
                evidence=[evidence],
                extractor="deterministic-regex",
            )
        )
    for match in _BATHS_RE.finditer(text):
        start, end = match.span(1)
        evidence = _evidence_for_span(snapshot.snapshot_id, start, end, "text", text)
        candidates.append(
            FieldCandidate(
                field_path="/listing/baths",
                value=match.group(1),
                confidence=0.8,
                evidence=[evidence],
                extractor="deterministic-regex",
            )
        )
    for match in _ADDRESS_RE.finditer(text):
        start, end = match.span()
        evidence = _evidence_for_span(snapshot.snapshot_id, start, end, "text", text)
        candidates.append(
            FieldCandidate(
                field_path="/listing/address",
                value=match.group(0).strip(),
                confidence=0.75,
                evidence=[evidence],
                extractor="deterministic-regex",
            )
        )
    for match in _AVAIL_RE.finditer(text):
        start, end = match.span()
        evidence = _evidence_for_span(snapshot.snapshot_id, start, end, "text", text)
        candidates.append(
            FieldCandidate(
                field_path="/listing/availability",
                value=match.group(0),
                confidence=0.7,
                evidence=[evidence],
                extractor="deterministic-regex",
            )
        )
    return candidates


def _candidate_key(candidate: FieldCandidate) -> str:
    payload = {
        "field_path": candidate.field_path,
        "value": candidate.value,
        "extractor": candidate.extractor,
        "evidence": [
            {
                "kind": ev.kind.value,
                "locator": ev.locator,
                "excerpt": ev.excerpt,
            }
            for ev in candidate.evidence
        ],
    }
    return sha256_text(json.dumps(payload, sort_keys=True, default=str))


@dataclass
class DeterministicExtractor:
    extractor_version: str = "deterministic/v1"

    def extract(self, snapshot: SnapshotContent) -> List[FieldCandidate]:
        candidates = _jsonld_candidates(snapshot) + _regex_candidates(snapshot)
        # Deterministic ordering and dedupe by full candidate payload.
        deduped: Dict[str, FieldCandidate] = {}
        for candidate in candidates:
            deduped[_candidate_key(candidate)] = candidate
        ordered = sorted(
            deduped.values(),
            key=lambda c: (c.field_path, str(c.value), c.extractor),
        )
        return ordered
