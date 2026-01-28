from typing import Dict, List, Optional

from services.snapshot_store.models import SnapshotRecord


class SnapshotRepository:
    def __init__(self) -> None:
        self._snapshots: Dict[str, SnapshotRecord] = {}
        self._by_hash: Dict[str, List[str]] = {}

    def add(self, snapshot: SnapshotRecord) -> None:
        self._snapshots[snapshot.snapshot_id] = snapshot
        self._by_hash.setdefault(snapshot.content_hash, []).append(snapshot.snapshot_id)

    def get(self, snapshot_id: str) -> Optional[SnapshotRecord]:
        return self._snapshots.get(snapshot_id)

    def list(self) -> List[SnapshotRecord]:
        return list(self._snapshots.values())

    def by_hash(self, content_hash: str) -> List[SnapshotRecord]:
        return [self._snapshots[sid] for sid in self._by_hash.get(content_hash, [])]

    def find_by_storage_refs(self, storage_refs: Dict[str, object]) -> List[SnapshotRecord]:
        return [
            snapshot
            for snapshot in self._snapshots.values()
            if snapshot.storage_refs == storage_refs
        ]
