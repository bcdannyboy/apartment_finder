from fastapi import FastAPI
from fastapi.responses import JSONResponse

from services.common.api import error_response, ok_response
from services.searchspec.repository import SearchSpecRepository
from services.searchspec.service import SearchSpecService

app = FastAPI(title="SearchSpec", docs_url=None, redoc_url=None)

_repository = SearchSpecRepository()
_service = SearchSpecService(_repository)


@app.post("/searchspec/parse")
def parse_searchspec(payload: dict):
    result = _service.create_from_payload(payload)
    if result.errors:
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "SearchSpec validation failed", {"errors": result.errors}),
        )
    assert result.record is not None
    spec = result.record.spec
    return ok_response({"search_spec_id": spec.search_spec_id, "schema_version": spec.schema_version})


@app.get("/searchspec/{search_spec_id}")
def fetch_searchspec(search_spec_id: str):
    spec = _service.get(search_spec_id)
    if spec is None:
        return JSONResponse(
            status_code=404,
            content=error_response("NOT_FOUND", "SearchSpec not found"),
        )
    payload = spec.model_dump() if hasattr(spec, "model_dump") else spec.dict()
    return ok_response({"search_spec": payload})
