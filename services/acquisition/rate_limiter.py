from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional


class Clock:
    def now(self) -> datetime:
        return datetime.now(tz=timezone.utc)


class FrozenClock(Clock):
    def __init__(self, now: Optional[datetime] = None) -> None:
        self._now = now or datetime.now(tz=timezone.utc)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now = self._now + timedelta(seconds=seconds)


@dataclass
class DomainPolicy:
    concurrency_cap: int = 1
    min_delay_seconds: float = 1.0
    error_backoff_seconds: float = 5.0
    max_backoff_seconds: float = 60.0
    budget_per_window: int = 60
    window_seconds: float = 60.0


@dataclass
class DomainState:
    inflight: int = 0
    last_request_at: Optional[datetime] = None
    error_count: int = 0
    cooldown_until: Optional[datetime] = None
    window_start: Optional[datetime] = None
    window_count: int = 0


class DomainRateLimiter:
    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock or Clock()
        self._policies: Dict[str, DomainPolicy] = {}
        self._state: Dict[str, DomainState] = {}

    def set_policy(self, domain: str, policy: DomainPolicy) -> None:
        self._policies[domain] = policy

    def policy_for(self, domain: str) -> DomainPolicy:
        return self._policies.get(domain, DomainPolicy())

    def state_for(self, domain: str) -> DomainState:
        if domain not in self._state:
            self._state[domain] = DomainState()
        return self._state[domain]

    def _refresh_window(self, domain: str, now: datetime) -> None:
        state = self.state_for(domain)
        policy = self.policy_for(domain)
        if state.window_start is None:
            state.window_start = now
            state.window_count = 0
            return
        if (now - state.window_start).total_seconds() >= policy.window_seconds:
            state.window_start = now
            state.window_count = 0

    def next_available_time(self, domain: str) -> datetime:
        now = self._clock.now()
        state = self.state_for(domain)
        policy = self.policy_for(domain)
        self._refresh_window(domain, now)

        candidate = now
        if state.last_request_at is not None:
            candidate = max(
                candidate,
                state.last_request_at + timedelta(seconds=policy.min_delay_seconds),
            )
        if state.cooldown_until is not None:
            candidate = max(candidate, state.cooldown_until)
        if state.window_start is not None and state.window_count >= policy.budget_per_window:
            candidate = max(
                candidate,
                state.window_start + timedelta(seconds=policy.window_seconds),
            )
        return candidate

    def can_acquire(self, domain: str) -> bool:
        now = self._clock.now()
        state = self.state_for(domain)
        policy = self.policy_for(domain)
        if state.inflight >= policy.concurrency_cap:
            return False
        return now >= self.next_available_time(domain)

    def acquire(self, domain: str) -> Optional[datetime]:
        now = self._clock.now()
        if not self.can_acquire(domain):
            return self.next_available_time(domain)
        state = self.state_for(domain)
        self._refresh_window(domain, now)
        state.inflight += 1
        state.last_request_at = now
        state.window_count += 1
        return None

    def release(self, domain: str, success: bool) -> None:
        state = self.state_for(domain)
        state.inflight = max(0, state.inflight - 1)
        if success:
            state.error_count = 0
            state.cooldown_until = None

    def register_error(self, domain: str) -> datetime:
        now = self._clock.now()
        state = self.state_for(domain)
        policy = self.policy_for(domain)
        state.error_count += 1
        backoff = policy.error_backoff_seconds * (2 ** (state.error_count - 1))
        backoff = min(backoff, policy.max_backoff_seconds)
        state.cooldown_until = now + timedelta(seconds=backoff)
        return state.cooldown_until
