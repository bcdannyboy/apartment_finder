from __future__ import annotations

import json
from typing import Any

from services.common.hashes import sha256_text


def stable_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def stable_hash(payload: Any) -> str:
    return sha256_text(stable_json(payload))
