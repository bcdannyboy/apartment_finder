from fastapi import FastAPI
from fastapi.responses import JSONResponse

from services.common.api import error_response, ok_response
from services.geo_commute.api_models import (
    CommuteRequestModel,
    GeocodeRequestModel,
    GtfsRegisterRequestModel,
)
from services.geo_commute.config import build_geo_commute_service
from services.geo_commute.models import CommuteRequest, GeocodeRequest, GeoCommuteError

app = FastAPI(title="Geo Commute", docs_url=None, redoc_url=None)

_service, _otp_manager, _repository = build_geo_commute_service()


def _model_dump(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


@app.post("/geo/geocode")
def geocode(request: GeocodeRequestModel):
    if request.schema_version != "v1":
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "schema_version must be v1"),
        )
    try:
        result = _service.geocode_address(
            GeocodeRequest(
                address=request.address,
                locality=request.locality,
                region=request.region,
                country=request.country,
            )
        )
    except GeoCommuteError as exc:
        return JSONResponse(
            status_code=400,
            content=error_response(exc.code, str(exc), exc.details),
        )
    _repository.add_geocode(
        GeocodeRequest(
            address=request.address,
            locality=request.locality,
            region=request.region,
            country=request.country,
        ),
        result,
    )
    return ok_response(
        {
            "provider": result.provider.value,
            "precision": result.precision.value,
            "confidence": result.confidence,
            "latitude": result.latitude,
            "longitude": result.longitude,
            "label": result.label,
            "metadata": result.metadata,
        }
    )


@app.post("/geo/commute")
def commute(request: CommuteRequestModel):
    if request.schema_version != "v1":
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "schema_version must be v1"),
        )
    try:
        result = _service.commute(
            CommuteRequest(
                origin_latitude=request.origin_latitude,
                origin_longitude=request.origin_longitude,
                destination_latitude=request.destination_latitude,
                destination_longitude=request.destination_longitude,
                mode=request.mode,
                depart_at=request.depart_at,
                origin_h3=request.origin_h3,
                anchor_id=request.anchor_id,
                gtfs_fingerprint=request.gtfs_fingerprint,
            )
        )
    except GeoCommuteError as exc:
        return JSONResponse(
            status_code=400,
            content=error_response(exc.code, str(exc), exc.details),
        )
    _repository.add_commute(
        CommuteRequest(
            origin_latitude=request.origin_latitude,
            origin_longitude=request.origin_longitude,
            destination_latitude=request.destination_latitude,
            destination_longitude=request.destination_longitude,
            mode=request.mode,
            depart_at=request.depart_at,
            origin_h3=request.origin_h3,
            anchor_id=request.anchor_id,
            gtfs_fingerprint=request.gtfs_fingerprint,
        ),
        result.route,
        cache_key=result.cache_key,
        cache_hit=result.cache_hit,
    )
    return ok_response(
        {
            "cache_key": result.cache_key,
            "cache_hit": result.cache_hit,
            "route": {
                "duration_min": result.route.duration_min,
                "distance_m": result.route.distance_m,
                "provider": result.route.provider.value,
                "mode": result.route.mode.value,
                "metadata": result.route.metadata,
            },
        }
    )


@app.post("/geo/gtfs/register")
def register_gtfs(request: GtfsRegisterRequestModel):
    if request.schema_version != "v1":
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "schema_version must be v1"),
        )
    if _otp_manager is None:
        return JSONResponse(
            status_code=400,
            content=error_response("GTFS_DISABLED", "GTFS storage is not configured"),
        )
    try:
        _otp_manager.register_feed(path=request.path, fingerprint=request.fingerprint)
        build = _otp_manager.ensure_graph()
    except GeoCommuteError as exc:
        return JSONResponse(
            status_code=400,
            content=error_response(exc.code, str(exc), exc.details),
        )
    return ok_response(
        {
            "fingerprint": build.fingerprint,
            "graph_version": build.graph_version,
        }
    )
