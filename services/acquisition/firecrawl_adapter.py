from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Protocol
from uuid import uuid4

from services.acquisition.errors import AdapterValidationError
from services.acquisition.models import AdapterLogRecord, FirecrawlRequest, FirecrawlResponse
from services.acquisition.repository import AdapterLogRepository
from services.acquisition.validation import ALLOWED_FORMATS
from services.common.hashes import sha256_text
from services.snapshot_store.models import SnapshotCreateRequest
from services.snapshot_store.service import SnapshotStoreService


class FirecrawlClient(Protocol):
    def fetch(self, request: FirecrawlRequest) -> FirecrawlResponse: ...


class FirecrawlAdapter:
    def __init__(
        self,
        *,
        client: FirecrawlClient,
        snapshot_store: SnapshotStoreService,
        adapter_log: Optional[AdapterLogRepository] = None,
    ) -> None:
        self._client = client
        self._snapshot_store = snapshot_store
        self._adapter_log = adapter_log

    def _log(self, *, task_id: Optional[str], request: Dict[str, Any], response: Optional[Dict[str, Any]]) -> None:
        if self._adapter_log is None:
            return
        record = AdapterLogRecord(
            log_id=str(uuid4()),
            task_id=task_id,
            request=request,
            response=response,
            created_at=datetime.now(tz=timezone.utc),
        )
        self._adapter_log.add(record)

    def _validate_request(self, request: FirecrawlRequest) -> None:
        if request.schema_version != "v1":
            raise AdapterValidationError("schema_version must be v1")
        if request.change_tracking is None:
            raise AdapterValidationError("change_tracking is required")
        formats = request.formats or {}
        unknown = set(formats.keys()) - ALLOWED_FORMATS
        if unknown:
            raise AdapterValidationError(f"Unsupported format field(s): {sorted(unknown)}")
        if not formats.get("markdown"):
            raise AdapterValidationError("change_tracking requires markdown format")

    def _fallback_content_hash(self, response: FirecrawlResponse) -> str:
        if response.content_hash:
            return response.content_hash
        if response.raw_content:
            return sha256_text(response.raw_content)
        if response.storage_refs:
            return SnapshotStoreService.deterministic_hash_from_refs(response.storage_refs)
        raise AdapterValidationError("content_hash missing and no raw_content available")

    def fetch_and_store(
        self,
        *,
        task_id: Optional[str],
        source_id: str,
        request: FirecrawlRequest,
    ):
        self._validate_request(request)
        request_payload = request.model_dump()
        self._log(task_id=task_id, request=request_payload, response=None)

        response = self._client.fetch(request)
        response_payload = response.model_dump()
        content_hash = self._fallback_content_hash(response)
        change_tracking = response.change_tracking or request.change_tracking
        storage_refs = response.storage_refs or {}

        snapshot_request = SnapshotCreateRequest(
            schema_version="v1",
            source_id=source_id,
            url=response.url,
            fetched_at=response.fetched_at,
            http_status=response.http_status,
            formats=response.formats,
            storage_refs=storage_refs,
            content_hash=content_hash,
            change_tracking=change_tracking,
            raw_content=response.raw_content,
            raw_metadata=response_payload,
        )
        snapshot = self._snapshot_store.create_snapshot(snapshot_request)
        self._log(task_id=task_id, request=request_payload, response=response_payload)
        return snapshot
