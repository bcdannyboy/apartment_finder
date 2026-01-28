from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from services.alerts.dispatchers import DisabledChannelAdapter
from services.alerts.models import AlertsDispatchRequest, AlertsRunRequest
from services.alerts.repository import AlertRepository
from services.alerts.service import AlertService
from services.common.api import error_response, ok_response
from services.common.enums import AlertChannel
from services.dedupe.service import ListingChangeStore
from services.ranking.service import RankingService
from services.retrieval.repository import ListingRepository
from services.retrieval.service import RetrievalService
from services.searchspec.repository import SearchSpecRepository
from services.searchspec.service import SearchSpecService

app = FastAPI(title="Alerts", docs_url=None, redoc_url=None)

_listing_repo = ListingRepository()
_retrieval = RetrievalService(_listing_repo)
_searchspec_repo = SearchSpecRepository()
_searchspec_service = SearchSpecService(_searchspec_repo)
_ranking = RankingService(listings=_listing_repo, retrieval=_retrieval)
_listing_changes = ListingChangeStore()
_alert_repo = AlertRepository()
_dispatchers = {
    AlertChannel.local: DisabledChannelAdapter(reason="local_notifications_unavailable"),
    AlertChannel.smtp: DisabledChannelAdapter(reason="smtp_not_configured"),
}
_alert_service = AlertService(
    _alert_repo,
    _searchspec_service,
    _ranking,
    _listing_repo,
    _listing_changes,
    dispatchers=_dispatchers,
)


def _parse_timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp


@app.post("/alerts/run")
def run_alerts(request: AlertsRunRequest):
    if request.schema_version != "v1":
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "schema_version must be v1"),
        )
    try:
        since = _parse_timestamp(request.since)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "since must be ISO timestamp"),
        )
    try:
        created = _alert_service.run(search_spec_id=request.search_spec_id, since=since)
    except KeyError:
        return JSONResponse(
            status_code=404,
            content=error_response("NOT_FOUND", "SearchSpec not found"),
        )
    return ok_response({"alerts_created": created})


@app.post("/alerts/dispatch")
def dispatch_alerts(request: AlertsDispatchRequest):
    if request.schema_version != "v1":
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", "schema_version must be v1"),
        )
    dispatched = _alert_service.dispatch(alert_ids=request.alert_ids, channel=request.channel)
    return ok_response({"dispatched": dispatched})
