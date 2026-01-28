from fastapi import FastAPI
from fastapi.responses import JSONResponse

from services.common.api import error_response, ok_response
from dataclasses import asdict, is_dataclass

from services.ranking.api_models import RankRequestModel
from services.ranking.models import RankingResult
from services.ranking.service import RankingService
from services.retrieval.repository import ListingRepository
from services.retrieval.service import RetrievalService
from services.searchspec.repository import SearchSpecRepository
from services.searchspec.service import SearchSpecService

app = FastAPI(title="Ranking", docs_url=None, redoc_url=None)

_listing_repo = ListingRepository()
_retrieval = RetrievalService(_listing_repo)
_searchspec_repo = SearchSpecRepository()
_searchspec_service = SearchSpecService(_searchspec_repo)
_service = RankingService(listings=_listing_repo, retrieval=_retrieval)


def _model_dump(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if is_dataclass(model):
        return asdict(model)
    return model.dict()


def _serialize_result(result: RankingResult) -> dict:
    return {
        "results": [
            {
                "listing_id": item.listing_id,
                "rank": item.rank,
                "scores": _model_dump(item.scores),
                "explanation": _model_dump(item.explanation),
            }
            for item in result.results
        ]
    }


@app.post("/rank")
def rank_listings(request: RankRequestModel):
    if request.schema_version != "v1":
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "schema_version must be v1"),
        )
    spec = _searchspec_service.get(request.search_spec_id)
    if spec is None:
        return JSONResponse(
            status_code=404,
            content=error_response("NOT_FOUND", "SearchSpec not found"),
        )
    limit = request.options.limit if request.options else 50
    result = _service.rank(spec, limit=limit)
    return ok_response(_serialize_result(result))
