from __future__ import annotations

import json
from typing import Any, Dict
from uuid import NAMESPACE_DNS, uuid5

from services.common.hashes import sha256_text


def stable_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def deterministic_id(label: str, payload: Dict[str, Any]) -> str:
    canonical = stable_json({"label": label, **payload})
    digest = sha256_text(canonical)
    return str(uuid5(NAMESPACE_DNS, digest))
