from fastapi import FastAPI
from fastapi.responses import JSONResponse

from services.common.api import error_response, ok_response
from services.policy_gate.models import PolicyEvaluateRequest
from services.policy_gate.policy_matrix import PolicyDecisionMatrix
from services.policy_gate.repository import PolicyRepository
from services.policy_gate.service import PolicyGateService

app = FastAPI(title="Policy Gate", docs_url=None, redoc_url=None)

_repository = PolicyRepository()
_matrix = PolicyDecisionMatrix()
_service = PolicyGateService(_repository, _matrix)


def _model_dump(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


@app.post("/policy/evaluate")
def evaluate_policy(request: PolicyEvaluateRequest):
    try:
        decision = _service.evaluate(request)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=error_response("VALIDATION_ERROR", str(exc)),
        )
    return ok_response(_model_dump(decision))
