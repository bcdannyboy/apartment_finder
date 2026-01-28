from datetime import datetime, timezone
from typing import Any, Dict, Optional

from services.acquisition.models import AuditLogRecord
from services.acquisition.repository import AuditLogRepository


class AuditLogger:
    def __init__(self, repository: AuditLogRepository) -> None:
        self._repository = repository

    def log(
        self,
        *,
        task_id: str,
        policy_id: Optional[str],
        outcome: str,
        params: Dict[str, Any],
        attempt: int,
        error_class: Optional[str] = None,
        source_id: Optional[str] = None,
        domain: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> AuditLogRecord:
        record = AuditLogRecord(
            audit_id=self._repository.new_id(),
            task_id=task_id,
            policy_id=policy_id,
            outcome=outcome,
            params=params,
            error_class=error_class,
            attempt=attempt,
            source_id=source_id,
            domain=domain,
            created_at=created_at or datetime.now(tz=timezone.utc),
        )
        self._repository.add(record)
        return record
