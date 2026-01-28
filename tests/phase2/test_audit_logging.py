from services.acquisition.rate_limiter import DomainPolicy
from services.acquisition.scheduler import TaskScheduler
from services.acquisition.worker import TaskWorker
from services.acquisition.errors import TransientNetworkError
from services.common.enums import PolicyStatus, TaskType


def _crawl_payload():
    return {
        "url": "https://example.com/listing",
        "formats": {"html": True, "markdown": True},
        "change_tracking": {"mode": "diff"},
    }


def _make_scheduler(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock):
    return TaskScheduler(
        queue=queue,
        repository=task_repo,
        policy_gate=policy_gate,
        audit_logger=audit_logger,
        rate_limiter=rate_limiter,
        clock=clock,
    )


def _make_worker(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock, handler):
    return TaskWorker(
        repository=task_repo,
        queue=queue,
        policy_gate=policy_gate,
        audit_logger=audit_logger,
        rate_limiter=rate_limiter,
        firecrawl_handler=handler,
        clock=clock,
    )


def test_audit_log_success_contains_required_fields(
    queue,
    task_repo,
    policy_gate,
    audit_logger,
    rate_limiter,
    clock,
    task_factory,
    policy_repo,
    audit_repo,
):
    policy_repo.upsert_policy(source_id="source-1", policy_status=PolicyStatus.crawl_allowed)
    scheduler = _make_scheduler(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock)
    worker = _make_worker(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock, lambda task: None)
    task = task_factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload=_crawl_payload(),
    )
    scheduler.submit_task(task)
    worker.process_task(task.task_id)
    record = audit_repo.list()[-1]
    assert record.outcome == "succeeded"
    assert record.policy_id is not None
    assert record.task_id == task.task_id
    assert record.source_id == "source-1"
    assert record.domain == "example.com"
    assert record.attempt == 1


def test_audit_log_denied_contains_reason(
    queue,
    task_repo,
    policy_gate,
    audit_logger,
    rate_limiter,
    clock,
    task_factory,
    policy_repo,
    audit_repo,
):
    policy_repo.upsert_policy(source_id="source-1", policy_status=PolicyStatus.manual_only)
    scheduler = _make_scheduler(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock)
    task = task_factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload=_crawl_payload(),
    )
    scheduler.submit_task(task)
    record = audit_repo.list()[-1]
    assert record.outcome == "denied"
    assert "reason" in record.params


def test_audit_log_retry_attempts_tracked(
    queue,
    task_repo,
    policy_gate,
    audit_logger,
    rate_limiter,
    clock,
    task_factory,
    policy_repo,
    audit_repo,
):
    policy_repo.upsert_policy(source_id="source-1", policy_status=PolicyStatus.crawl_allowed)
    rate_limiter.set_policy("example.com", DomainPolicy(error_backoff_seconds=1, max_backoff_seconds=2))

    def handler(task):
        raise TransientNetworkError("network")

    scheduler = _make_scheduler(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock)
    worker = _make_worker(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock, handler)
    task = task_factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload=_crawl_payload(),
        max_attempts=2,
    )
    scheduler.submit_task(task)
    worker.process_task(task.task_id)
    clock.advance(2)
    worker.process_task(task.task_id)
    records = [record for record in audit_repo.list() if record.task_id == task.task_id]
    assert records[0].attempt == 1
    assert records[0].error_class == "TransientNetworkError"
    assert records[-1].attempt == 2
