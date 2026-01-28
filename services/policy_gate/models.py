from typing import List, Optional

from pydantic import BaseModel

from services.common.enums import PolicyStatus, TaskType


class PolicyEvaluateRequest(BaseModel):
    schema_version: str
    source_id: str
    domain: str
    task_type: TaskType
    requested_operation: str


class PolicyDecisionData(BaseModel):
    decision: PolicyStatus
    allowed_operations: List[TaskType]
    reason: str
    policy_id: Optional[str]
