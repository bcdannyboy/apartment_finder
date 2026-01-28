from typing import Any, Dict, Optional


SCHEMA_VERSION = "v1"


def ok_response(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        "data": data,
    }


def error_response(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "error",
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }
