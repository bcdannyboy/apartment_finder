from services.acquisition.scheduler import TaskScheduler
from services.acquisition.worker import TaskWorker
from services.common.enums import PolicyStatus, TaskType


class CallTracker:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, task):
        self.calls.append(task.task_id)
        return {"ok": True}


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


def _crawl_payload():
    return {
        "url": "https://example.com/listing",
        "formats": {"html": True, "markdown": True},
        "change_tracking": {"mode": "diff"},
    }


def test_policy_gate_allows_crawl_allowed_and_blocks_manual_only(
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
    handler = CallTracker()
    worker = _make_worker(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock, handler)

    task = task_factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload=_crawl_payload(),
    )
    submitted = scheduler.submit_task(task)
    assert submitted is not None
    worker.process_task(task.task_id)
    assert task_repo.get(task.task_id).status.value == "succeeded"
    assert handler.calls == [task.task_id]

    policy_repo.upsert_policy(source_id="source-2", policy_status=PolicyStatus.manual_only)
    denied = task_factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-2",
        policy_id="policy-2",
        domain="example.com",
        payload=_crawl_payload(),
    )
    blocked = scheduler.submit_task(denied)
    assert blocked is None
    assert audit_repo.list()[-1].outcome == "denied"


def test_policy_gate_blocks_unknown_and_partner_required(
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
    scheduler = _make_scheduler(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock)
    policy_repo.upsert_policy(source_id="source-partner", policy_status=PolicyStatus.partner_required)

    partner_task = task_factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-partner",
        policy_id="policy-1",
        domain="example.com",
        payload=_crawl_payload(),
    )
    assert scheduler.submit_task(partner_task) is None
    assert audit_repo.list()[-1].outcome == "denied"

    unknown_task = task_factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-unknown",
        policy_id="policy-2",
        domain="example.com",
        payload=_crawl_payload(),
    )
    assert scheduler.submit_task(unknown_task) is None
    assert audit_repo.list()[-1].outcome == "denied"


def test_policy_change_blocks_execution(
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
    handler = CallTracker()
    worker = _make_worker(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock, handler)

    task = task_factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload=_crawl_payload(),
    )
    assert scheduler.submit_task(task) is not None

    policy_repo.upsert_policy(source_id="source-1", policy_status=PolicyStatus.manual_only)
    worker.process_task(task.task_id)
    assert task_repo.get(task.task_id).status.value == "denied"
    assert audit_repo.list()[-1].outcome == "denied"


def test_manual_only_sources_allow_import_task_only(
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
    handler = CallTracker()
    worker = _make_worker(queue, task_repo, policy_gate, audit_logger, rate_limiter, clock, handler)

    for task_type in (TaskType.SearchTask, TaskType.MapTask, TaskType.CrawlTask, TaskType.ScrapeTask):
        blocked = task_factory.create_task(
            task_type=task_type,
            source_id="source-1",
            policy_id="policy-1",
            domain="example.com",
            payload=_crawl_payload(),
        )
        assert scheduler.submit_task(blocked) is None
        assert audit_repo.list()[-1].outcome == "denied"

    import_task = task_factory.create_task(
        task_type=TaskType.ImportTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload={"source": "manual_upload"},
    )
    submitted = scheduler.submit_task(import_task)
    assert submitted is not None
    worker.process_task(import_task.task_id)
    assert task_repo.get(import_task.task_id).status.value == "succeeded"
