from services.common.enums import PolicyStatus
from services.policy_gate.models import PolicyDecisionData, PolicyEvaluateRequest
from services.policy_gate.policy_matrix import PolicyDecisionMatrix
from services.policy_gate.repository import PolicyRepository


class PolicyGateService:
    def __init__(self, repository: PolicyRepository, matrix: PolicyDecisionMatrix) -> None:
        self._repository = repository
        self._matrix = matrix

    def evaluate(self, request: PolicyEvaluateRequest) -> PolicyDecisionData:
        if request.schema_version != "v1":
            raise ValueError("schema_version must be v1")

        policy = self._repository.get_policy(request.source_id)
        status = policy.policy_status if policy else PolicyStatus.unknown
        decision = self._matrix.evaluate(
            status=status,
            task_type=request.task_type,
            requested_operation=request.requested_operation,
        )

        return PolicyDecisionData(
            decision=decision.decision,
            allowed_operations=decision.allowed_operations,
            reason=decision.reason,
            policy_id=policy.policy_id if policy else None,
        )
