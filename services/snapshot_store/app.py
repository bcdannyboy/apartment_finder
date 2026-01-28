from fastapi import FastAPI
from fastapi.responses import JSONResponse

from services.common.api import error_response, ok_response
from services.snapshot_store.models import SnapshotCreateRequest
from services.snapshot_store.repository import SnapshotRepository
from services.snapshot_store.service import SnapshotStoreService

app = FastAPI(title="Snapshot Store", docs_url=None, redoc_url=None)

_repository = SnapshotRepository()
_service = SnapshotStoreService(_repository)


def _model_dump(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


@app.post("/snapshots")
def create_snapshot(request: SnapshotCreateRequest):
    try:
        record = _service.create_snapshot(request)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", str(exc)),
        )
    return ok_response({"snapshot_id": record.snapshot_id, "content_hash": record.content_hash})


@app.get("/snapshots/{snapshot_id}")
def fetch_snapshot(snapshot_id: str):
    try:
        record = _service.get_snapshot(snapshot_id)
    except KeyError:
        return JSONResponse(
            status_code=404,
            content=error_response("NOT_FOUND", "Snapshot not found"),
        )
    payload = _model_dump(record)
    payload["raw_refs"] = payload.get("storage_refs")
    return ok_response(
        {
            "snapshot_id": payload["snapshot_id"],
            "url": payload["url"],
            "content_hash": payload["content_hash"],
            "formats": payload["formats"],
            "storage_refs": payload["storage_refs"],
            "raw_refs": payload["raw_refs"],
        }
    )


@app.get("/snapshots")
def list_snapshots():
    records = [_model_dump(record) for record in _service.list_snapshots()]
    for record in records:
        record["raw_refs"] = record.get("storage_refs")
    return ok_response({"snapshots": records})
