from services.acquisition.factory import TaskFactory
from services.acquisition.queue import InMemoryQueueAdapter
from services.acquisition.scheduler import TaskScheduler
from services.acquisition.repository import AuditLogRepository, TaskRepository
from services.acquisition.audit import AuditLogger
from services.acquisition.rate_limiter import DomainRateLimiter, FrozenClock
from services.common.enums import PolicyStatus, TaskType
from services.policy_gate.policy_matrix import PolicyDecisionMatrix
from services.policy_gate.repository import PolicyRepository
from services.policy_gate.service import PolicyGateService


def _payload(url: str):
    return {
        "url": url,
        "formats": {"html": True, "markdown": True},
        "change_tracking": {"mode": "diff"},
    }


def test_task_id_is_deterministic_for_same_inputs():
    factory = TaskFactory(seed="seed-1")
    task_a = factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload=_payload("https://example.com/a"),
    )
    task_b = factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload=_payload("https://example.com/a"),
    )
    assert task_a.task_id == task_b.task_id


def test_dedupe_produces_stable_task_set():
    factory = TaskFactory(seed="seed-1")
    task_a = factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload=_payload("https://example.com/a"),
    )
    task_b = factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload=_payload("https://example.com/a"),
    )
    deduped = factory.dedupe([task_a, task_b])
    assert [task.task_id for task in deduped] == [task_a.task_id]


def test_scheduler_is_deterministic_for_same_inputs():
    policy_repo = PolicyRepository()
    policy_repo.upsert_policy(source_id="source-1", policy_status=PolicyStatus.crawl_allowed)
    policy_gate = PolicyGateService(policy_repo, PolicyDecisionMatrix())
    queue = InMemoryQueueAdapter()
    repo = TaskRepository()
    audit_logger = AuditLogger(AuditLogRepository())
    clock = FrozenClock()
    rate_limiter = DomainRateLimiter(clock)
    scheduler = TaskScheduler(
        queue=queue,
        repository=repo,
        policy_gate=policy_gate,
        audit_logger=audit_logger,
        rate_limiter=rate_limiter,
        clock=clock,
    )

    factory = TaskFactory(seed="seed-1")
    scheduled_at = clock.now()
    task1 = factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload=_payload("https://example.com/a"),
        scheduled_at=scheduled_at,
        created_at=scheduled_at,
    )
    task2 = factory.create_task(
        task_type=TaskType.CrawlTask,
        source_id="source-1",
        policy_id="policy-1",
        domain="example.com",
        payload=_payload("https://example.com/b"),
        scheduled_at=scheduled_at,
        created_at=scheduled_at,
    )
    scheduler.submit_tasks([task2, task1])
    ordered = [item.task_id for item in queue.list()]
    assert ordered == sorted([task1.task_id, task2.task_id])
