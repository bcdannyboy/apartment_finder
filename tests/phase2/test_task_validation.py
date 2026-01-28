from datetime import datetime, timezone

from services.acquisition.scheduler import TaskScheduler
from services.common.enums import PolicyStatus, TaskType


def _base_payload():
    return {
        "task_id": "task-1",
        "task_type": TaskType.CrawlTask,
        "source_id": "source-1",
        "policy_id": "policy-1",
        "domain": "example.com",
        "payload": {
            "url": "https://example.com/listing",
            "formats": {"html": True, "markdown": True},
            "change_tracking": {"mode": "diff"},
        },
        "status": "queued",
        "attempt": 0,
        "max_attempts": 2,
        "scheduled_at": datetime(2026, 1, 28, tzinfo=timezone.utc),
        "created_at": datetime(2026, 1, 28, tzinfo=timezone.utc),
    }


def test_task_schema_missing_required_field_denied(
    queue, task_repo, policy_gate, audit_logger, rate_limiter, clock, audit_repo
):
    scheduler = TaskScheduler(
        queue=queue,
        repository=task_repo,
        policy_gate=policy_gate,
        audit_logger=audit_logger,
        rate_limiter=rate_limiter,
        clock=clock,
    )
    payload = _base_payload()
    payload.pop("source_id")
    result = scheduler.submit_raw(payload)
    assert result is None
    assert queue.list() == []
    records = audit_repo.list()
    assert records
    assert records[-1].error_class == "TaskValidationError"


def test_task_schema_invalid_task_type_denied(
    queue, task_repo, policy_gate, audit_logger, rate_limiter, clock, audit_repo
):
    scheduler = TaskScheduler(
        queue=queue,
        repository=task_repo,
        policy_gate=policy_gate,
        audit_logger=audit_logger,
        rate_limiter=rate_limiter,
        clock=clock,
    )
    payload = _base_payload()
    payload["task_type"] = "BadTask"
    result = scheduler.submit_raw(payload)
    assert result is None
    assert queue.list() == []
    records = audit_repo.list()
    assert records[-1].error_class == "TaskValidationError"


def test_queue_payload_missing_policy_or_domain_rejected(
    queue, task_repo, policy_gate, audit_logger, rate_limiter, clock, audit_repo, task_factory, policy_repo
):
    policy_repo.upsert_policy(source_id="source-1", policy_status=PolicyStatus.crawl_allowed)
    scheduler = TaskScheduler(
        queue=queue,
        repository=task_repo,
        policy_gate=policy_gate,
        audit_logger=audit_logger,
        rate_limiter=rate_limiter,
        clock=clock,
    )
    task = task_factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="",
        domain="example.com",
        payload={
            "url": "https://example.com/listing",
            "formats": {"html": True, "markdown": True},
            "change_tracking": {"mode": "diff"},
        },
    )
    result = scheduler.submit_task(task)
    assert result is None
    assert queue.list() == []
    assert audit_repo.list()[-1].error_class == "QueuePayloadError"


def test_queue_payload_rejects_unsupported_format(
    queue, task_repo, policy_gate, audit_logger, rate_limiter, clock, audit_repo, task_factory, policy_repo
):
    policy_repo.upsert_policy(source_id="source-1", policy_status=PolicyStatus.crawl_allowed)
    scheduler = TaskScheduler(
        queue=queue,
        repository=task_repo,
        policy_gate=policy_gate,
        audit_logger=audit_logger,
        rate_limiter=rate_limiter,
        clock=clock,
    )
    task = task_factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload={
            "url": "https://example.com/listing",
            "formats": {"html": True, "markdown": True, "unsupported": True},
            "change_tracking": {"mode": "diff"},
        },
    )
    result = scheduler.submit_task(task)
    assert result is None
    assert queue.list() == []
    assert audit_repo.list()[-1].error_class == "QueuePayloadError"
