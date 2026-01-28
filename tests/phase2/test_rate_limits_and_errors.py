from datetime import timedelta

from services.acquisition.rate_limiter import DomainPolicy
from services.acquisition.scheduler import TaskScheduler
from services.acquisition.worker import TaskWorker
from services.acquisition.errors import TransientNetworkError, UpstreamRateLimitError
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


def test_rate_limit_concurrency_cap_defers(
    queue,
    task_repo,
    policy_gate,
    audit_logger,
    rate_limiter,
    clock,
    task_factory,
    policy_repo,
):
    policy_repo.upsert_policy(source_id="source-1", policy_status=PolicyStatus.crawl_allowed)
    rate_limiter.set_policy("example.com", DomainPolicy(concurrency_cap=1, min_delay_seconds=1))
    state = rate_limiter.state_for("example.com")
    state.inflight = 1

    scheduler = _make_scheduler(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock)
    worker = _make_worker(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock, lambda task: None)
    task = task_factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload=_crawl_payload(),
        scheduled_at=clock.now(),
        created_at=clock.now(),
    )
    scheduler.submit_task(task)
    worker.process_task(task.task_id)
    assert task_repo.get(task.task_id).attempt == 0


def test_rate_limit_min_delay_enforced(
    queue,
    task_repo,
    policy_gate,
    audit_logger,
    rate_limiter,
    clock,
    task_factory,
    policy_repo,
):
    policy_repo.upsert_policy(source_id="source-1", policy_status=PolicyStatus.crawl_allowed)
    rate_limiter.set_policy("example.com", DomainPolicy(concurrency_cap=1, min_delay_seconds=10))
    state = rate_limiter.state_for("example.com")
    state.last_request_at = clock.now()

    scheduler = _make_scheduler(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock)
    worker = _make_worker(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock, lambda task: None)
    task = task_factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload=_crawl_payload(),
        scheduled_at=clock.now(),
        created_at=clock.now(),
    )
    scheduler.submit_task(task)
    worker.process_task(task.task_id)
    queued = queue.list()[-1]
    assert queued.scheduled_at >= clock.now() + timedelta(seconds=10)


def test_rate_limit_error_backoff_applied(
    queue,
    task_repo,
    policy_gate,
    audit_logger,
    rate_limiter,
    clock,
    task_factory,
    policy_repo,
):
    policy_repo.upsert_policy(source_id="source-1", policy_status=PolicyStatus.crawl_allowed)
    rate_limiter.set_policy("example.com", DomainPolicy(error_backoff_seconds=5, max_backoff_seconds=30))

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
        scheduled_at=clock.now(),
        created_at=clock.now(),
    )
    scheduler.submit_task(task)
    worker.process_task(task.task_id)
    state = rate_limiter.state_for("example.com")
    assert state.cooldown_until is not None
    queued = queue.list()[-1]
    assert queued.scheduled_at == state.cooldown_until


def test_rate_limit_budget_enforced(
    queue,
    task_repo,
    policy_gate,
    audit_logger,
    rate_limiter,
    clock,
    task_factory,
    policy_repo,
):
    policy_repo.upsert_policy(source_id="source-1", policy_status=PolicyStatus.crawl_allowed)
    rate_limiter.set_policy("example.com", DomainPolicy(budget_per_window=1, window_seconds=60))
    state = rate_limiter.state_for("example.com")
    state.window_start = clock.now()
    state.window_count = 1

    scheduler = _make_scheduler(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock)
    worker = _make_worker(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock, lambda task: None)
    task = task_factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload=_crawl_payload(),
        scheduled_at=clock.now(),
        created_at=clock.now(),
    )
    scheduler.submit_task(task)
    worker.process_task(task.task_id)
    queued = queue.list()[-1]
    assert queued.scheduled_at >= state.window_start + timedelta(seconds=60)


def test_transient_network_error_retries_with_backoff(
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
    rate_limiter.set_policy("example.com", DomainPolicy(error_backoff_seconds=5, max_backoff_seconds=30))

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
        scheduled_at=clock.now(),
        created_at=clock.now(),
    )
    scheduler.submit_task(task)
    worker.process_task(task.task_id)
    assert task_repo.get(task.task_id).attempt == 1
    assert audit_repo.list()[-1].error_class == "TransientNetworkError"


def test_upstream_rate_limit_error_reschedules(
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
    rate_limiter.set_policy("example.com", DomainPolicy(error_backoff_seconds=5, max_backoff_seconds=30))

    def handler(task):
        raise UpstreamRateLimitError("rate limit")

    scheduler = _make_scheduler(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock)
    worker = _make_worker(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock, handler)
    task = task_factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload=_crawl_payload(),
        max_attempts=2,
        scheduled_at=clock.now(),
        created_at=clock.now(),
    )
    scheduler.submit_task(task)
    worker.process_task(task.task_id)
    assert audit_repo.list()[-1].error_class == "UpstreamRateLimitError"
    queued = queue.list()[-1]
    assert queued.scheduled_at == rate_limiter.state_for("example.com").cooldown_until


def test_max_retry_exceeded_marks_failed(
    queue,
    task_repo,
    policy_gate,
    audit_logger,
    rate_limiter,
    clock,
    task_factory,
    policy_repo,
):
    policy_repo.upsert_policy(source_id="source-1", policy_status=PolicyStatus.crawl_allowed)

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
        max_attempts=1,
        scheduled_at=clock.now(),
        created_at=clock.now(),
    )
    scheduler.submit_task(task)
    worker.process_task(task.task_id)
    assert task_repo.get(task.task_id).status.value == "failed"
