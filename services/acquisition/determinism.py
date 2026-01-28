import json
from typing import Any, Dict, Iterable, List
from uuid import NAMESPACE_DNS, uuid5

from services.common.hashes import sha256_text


def stable_json_dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def deterministic_task_id(*, seed: str, task_type: str, source_id: str, domain: str, payload: Dict[str, Any]) -> str:
    canonical = stable_json_dumps(
        {
            "task_type": task_type,
            "source_id": source_id,
            "domain": domain,
            "payload": payload,
            "seed": seed,
        }
    )
    digest = sha256_text(canonical)
    return str(uuid5(NAMESPACE_DNS, digest))


def dedupe_task_ids(task_ids: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for task_id in task_ids:
        if task_id in seen:
            continue
        seen.add(task_id)
        ordered.append(task_id)
    return ordered
