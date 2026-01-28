from typing import Any, Dict, Optional

from pydantic import BaseModel


class SnapshotCreateRequest(BaseModel):
    schema_version: str
    source_id: str
    url: str
    fetched_at: str
    http_status: int
    formats: Dict[str, Any]
    storage_refs: Optional[Dict[str, Any]] = None
    raw_refs: Optional[Dict[str, Any]] = None
    content_hash: Optional[str] = None
    change_tracking: Optional[Dict[str, Any]] = None
    raw_metadata: Optional[Dict[str, Any]] = None
    raw_content: Optional[str] = None


class SnapshotRecord(BaseModel):
    snapshot_id: str
    source_id: str
    url: str
    fetched_at: str
    http_status: int
    content_hash: str
    formats: Dict[str, Any]
    storage_refs: Dict[str, Any]
    change_tracking: Optional[Dict[str, Any]] = None
    raw_metadata: Optional[Dict[str, Any]] = None
    immutable: bool = True
