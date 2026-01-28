from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from services.alerts.repository import AlertRecord


@dataclass(frozen=True)
class DispatchResult:
    success: bool
    retryable: bool = False
    error: Optional[str] = None


class AlertDispatchError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class AlertChannelAdapter(Protocol):
    def send(self, alert: AlertRecord) -> DispatchResult:
        ...


class DisabledChannelAdapter:
    def __init__(self, *, reason: str, retryable: bool = True) -> None:
        self._reason = reason
        self._retryable = retryable

    def send(self, alert: AlertRecord) -> DispatchResult:
        return DispatchResult(success=False, retryable=self._retryable, error=self._reason)
