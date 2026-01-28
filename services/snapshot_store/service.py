import json
from typing import Dict, List
from uuid import uuid4

from services.common.hashes import sha256_text
from services.snapshot_store.models import SnapshotCreateRequest, SnapshotRecord
from services.snapshot_store.repository import SnapshotRepository


class SnapshotStoreService:
    def __init__(self, repository: SnapshotRepository) -> None:
        self._repository = repository

    def create_snapshot(self, request: SnapshotCreateRequest) -> SnapshotRecord:
        if request.schema_version != "v1":
            raise ValueError("schema_version must be v1")

        storage_refs = request.storage_refs or request.raw_refs or {}
        content_hash = request.content_hash
        if not content_hash:
            if request.raw_content is None:
                raise ValueError("content_hash is required when raw_content is missing")
            content_hash = sha256_text(request.raw_content)

        if request.raw_content is None and request.content_hash:
            content_hash = request.content_hash

        record = SnapshotRecord(
            snapshot_id=str(uuid4()),
            source_id=request.source_id,
            url=request.url,
            fetched_at=request.fetched_at,
            http_status=request.http_status,
            content_hash=content_hash,
            formats=request.formats,
            storage_refs=storage_refs,
            change_tracking=request.change_tracking,
            raw_metadata=request.raw_metadata,
            immutable=True,
        )
        self._repository.add(record)
        return record

    def get_snapshot(self, snapshot_id: str) -> SnapshotRecord:
        snapshot = self._repository.get(snapshot_id)
        if snapshot is None:
            raise KeyError("snapshot not found")
        return snapshot

    def list_snapshots(self) -> List[SnapshotRecord]:
        return self._repository.list()

    def find_by_storage_refs(self, storage_refs: Dict[str, object]) -> List[SnapshotRecord]:
        return self._repository.find_by_storage_refs(storage_refs)

    @staticmethod
    def deterministic_hash_from_refs(storage_refs: Dict[str, object]) -> str:
        return sha256_text(json.dumps(storage_refs, sort_keys=True))
