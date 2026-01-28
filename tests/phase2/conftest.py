from datetime import datetime, timezone

import pytest

from services.acquisition.audit import AuditLogger
from services.acquisition.factory import TaskFactory
from services.acquisition.queue import InMemoryQueueAdapter
from services.acquisition.rate_limiter import DomainRateLimiter, FrozenClock
from services.acquisition.repository import AdapterLogRepository, AuditLogRepository, TaskRepository
from services.policy_gate.policy_matrix import PolicyDecisionMatrix
from services.policy_gate.repository import PolicyRepository
from services.policy_gate.service import PolicyGateService
from services.snapshot_store.repository import SnapshotRepository
from services.snapshot_store.service import SnapshotStoreService


@pytest.fixture
def clock():
    return FrozenClock(datetime(2026, 1, 28, tzinfo=timezone.utc))


@pytest.fixture
def policy_repo():
    return PolicyRepository()


@pytest.fixture
def policy_gate(policy_repo):
    return PolicyGateService(policy_repo, PolicyDecisionMatrix())


@pytest.fixture
def task_repo():
    return TaskRepository()


@pytest.fixture
def audit_repo():
    return AuditLogRepository()


@pytest.fixture
def audit_logger(audit_repo):
    return AuditLogger(audit_repo)


@pytest.fixture
def queue():
    return InMemoryQueueAdapter()


@pytest.fixture
def rate_limiter(clock):
    return DomainRateLimiter(clock)


@pytest.fixture
def task_factory():
    return TaskFactory(seed="phase2-seed")


@pytest.fixture
def adapter_log():
    return AdapterLogRepository()


@pytest.fixture
def snapshot_store():
    return SnapshotStoreService(SnapshotRepository())
