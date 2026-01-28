class TaskValidationError(ValueError):
    pass


class QueuePayloadError(ValueError):
    pass


class PolicyDeniedError(PermissionError):
    pass


class RateLimitError(RuntimeError):
    def __init__(self, message: str, next_allowed_at=None) -> None:
        super().__init__(message)
        self.next_allowed_at = next_allowed_at


class AdapterValidationError(ValueError):
    pass


class TransientNetworkError(RuntimeError):
    pass


class UpstreamRateLimitError(RuntimeError):
    pass
