from dataclasses import dataclass
from typing import Dict, Optional
from uuid import uuid4

from services.common.enums import PolicyStatus


@dataclass
class SourcePolicyRecord:
    policy_id: str
    source_id: str
    policy_status: PolicyStatus


class PolicyRepository:
    def __init__(self) -> None:
        self._policies: Dict[str, SourcePolicyRecord] = {}

    def upsert_policy(
        self,
        *,
        source_id: str,
        policy_status: PolicyStatus,
        policy_id: Optional[str] = None,
    ) -> SourcePolicyRecord:
        record = SourcePolicyRecord(
            policy_id=policy_id or str(uuid4()),
            source_id=source_id,
            policy_status=policy_status,
        )
        self._policies[source_id] = record
        return record

    def get_policy(self, source_id: str) -> Optional[SourcePolicyRecord]:
        return self._policies.get(source_id)
