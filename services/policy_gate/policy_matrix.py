from dataclasses import dataclass
from typing import Dict, List

from services.common.enums import PolicyStatus, TaskType


ALL_TASKS = [
    TaskType.SearchTask,
    TaskType.MapTask,
    TaskType.CrawlTask,
    TaskType.ScrapeTask,
    TaskType.ImportTask,
]


@dataclass(frozen=True)
class PolicyDecision:
    decision: PolicyStatus
    allowed_operations: List[TaskType]
    reason: str


class PolicyDecisionMatrix:
    def __init__(self) -> None:
        self._rules: Dict[PolicyStatus, List[TaskType]] = {
            PolicyStatus.crawl_allowed: list(ALL_TASKS),
            PolicyStatus.manual_only: [TaskType.ImportTask],
            PolicyStatus.partner_required: [],
            PolicyStatus.unknown: [],
        }

    def allowed_operations(self, status: PolicyStatus) -> List[TaskType]:
        return list(self._rules.get(status, []))

    def evaluate(
        self, *, status: PolicyStatus, task_type: TaskType, requested_operation: str
    ) -> PolicyDecision:
        allowed = self.allowed_operations(status)
        if status == PolicyStatus.crawl_allowed:
            reason = "crawl_allowed: automation permitted"
        elif status == PolicyStatus.manual_only:
            reason = "manual_only: ImportTask only"
        elif status == PolicyStatus.partner_required:
            reason = "partner_required: automation blocked until review"
        else:
            reason = "unknown: automation blocked until review"

        if task_type not in allowed:
            reason = f"{reason}; requested {task_type} denied"

        if requested_operation != "automated_fetch":
            reason = f"{reason}; requested_operation={requested_operation}"

        return PolicyDecision(decision=status, allowed_operations=allowed, reason=reason)
