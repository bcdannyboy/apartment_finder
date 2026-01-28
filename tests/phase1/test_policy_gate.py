import copy

import pytest
from fastapi.testclient import TestClient

import services.policy_gate.app as policy_app
from services.common.enums import PolicyStatus, TaskType
from services.policy_gate.models import PolicyEvaluateRequest
from services.policy_gate.policy_matrix import PolicyDecisionMatrix
from services.policy_gate.repository import PolicyRepository
from services.policy_gate.service import PolicyGateService
from services.policy_gate.tasks import route_task


def test_policy_gate_decisions_and_determinism():
    repo = PolicyRepository()
    repo.upsert_policy(source_id="source-1", policy_status=PolicyStatus.crawl_allowed)
    repo.upsert_policy(source_id="source-2", policy_status=PolicyStatus.manual_only)
    repo.upsert_policy(source_id="source-3", policy_status=PolicyStatus.partner_required)

    matrix = PolicyDecisionMatrix()
    service = PolicyGateService(repo, matrix)

    request = {
        "schema_version": "v1",
        "source_id": "source-1",
        "domain": "example.com",
        "task_type": TaskType.CrawlTask,
        "requested_operation": "automated_fetch",
    }
    decision_one = service.evaluate(PolicyEvaluateRequest(**request))
    decision_two = service.evaluate(PolicyEvaluateRequest(**copy.deepcopy(request)))
    assert decision_one.decision == decision_two.decision
    assert decision_one.allowed_operations == decision_two.allowed_operations
    assert decision_one.reason == decision_two.reason
    assert decision_one.decision == PolicyStatus.crawl_allowed
    assert TaskType.CrawlTask in decision_one.allowed_operations

    manual_request = PolicyEvaluateRequest(
        schema_version="v1",
        source_id="source-2",
        domain="example.com",
        task_type=TaskType.CrawlTask,
        requested_operation="automated_fetch",
    )
    manual_decision = service.evaluate(manual_request)
    assert manual_decision.decision == PolicyStatus.manual_only
    assert manual_decision.allowed_operations == [TaskType.ImportTask]

    partner_request = PolicyEvaluateRequest(
        schema_version="v1",
        source_id="source-3",
        domain="example.com",
        task_type=TaskType.CrawlTask,
        requested_operation="automated_fetch",
    )
    partner_decision = service.evaluate(partner_request)
    assert partner_decision.decision == PolicyStatus.partner_required
    assert partner_decision.allowed_operations == []
    assert "blocked" in partner_decision.reason

    unknown_request = PolicyEvaluateRequest(
        schema_version="v1",
        source_id="missing",
        domain="example.com",
        task_type=TaskType.CrawlTask,
        requested_operation="automated_fetch",
    )
    unknown_decision = service.evaluate(unknown_request)
    assert unknown_decision.decision == PolicyStatus.unknown
    assert unknown_decision.allowed_operations == []
    assert "blocked" in unknown_decision.reason


def test_policy_gate_api_contract_and_import_task():
    client = TestClient(policy_app.app)
    policy_app._repository.upsert_policy(
        source_id="source-api", policy_status=PolicyStatus.manual_only
    )

    response = client.post(
        "/policy/evaluate",
        json={
            "schema_version": "v1",
            "source_id": "source-api",
            "domain": "example.com",
            "task_type": "CrawlTask",
            "requested_operation": "automated_fetch",
        },
    )
    payload = response.json()
    assert payload["schema_version"] == "v1"
    assert payload["status"] == "ok"
    data = payload["data"]
    assert data["decision"] == PolicyStatus.manual_only.value
    assert data["allowed_operations"] == [TaskType.ImportTask.value]

    matrix = PolicyDecisionMatrix()
    decision = matrix.evaluate(
        status=PolicyStatus.manual_only,
        task_type=TaskType.CrawlTask,
        requested_operation="automated_fetch",
    )
    task = route_task(
        decision=decision,
        requested_task=TaskType.CrawlTask,
        source_id="source-api",
        policy_id=None,
    )
    assert task.task_type == TaskType.ImportTask

    blocked_decision = matrix.evaluate(
        status=PolicyStatus.partner_required,
        task_type=TaskType.CrawlTask,
        requested_operation="automated_fetch",
    )
    with pytest.raises(ValueError):
        route_task(
            decision=blocked_decision,
            requested_task=TaskType.CrawlTask,
            source_id="source-api",
            policy_id=None,
        )
