from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from services.common.enums import PolicyStatus, TaskType
from services.policy_gate.policy_matrix import PolicyDecision


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    task_type: TaskType
    source_id: str
    policy_id: Optional[str]


def route_task(
    *,
    decision: PolicyDecision,
    requested_task: TaskType,
    source_id: str,
    policy_id: Optional[str],
) -> TaskRecord:
    if decision.decision == PolicyStatus.manual_only:
        task_type = TaskType.ImportTask
    elif requested_task in decision.allowed_operations:
        task_type = requested_task
    else:
        raise ValueError("Automation denied by policy")

    return TaskRecord(
        task_id=str(uuid4()),
        task_type=task_type,
        source_id=source_id,
        policy_id=policy_id,
    )
