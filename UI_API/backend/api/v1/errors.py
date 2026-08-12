"""Safe error envelopes for versioned API routes without changing legacy errors."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from modules.operations import _observability as observability_service

_ERRORS = {
    400: ("bad_request", "The request is invalid."),
    401: ("unauthorized", "Authentication is required."),
    403: ("forbidden", "The action is not allowed."),
    404: ("not_found", "The resource was not found."),
    409: ("conflict", "The request conflicts with current state."),
    422: ("validation_error", "Request validation failed."),
    429: ("rate_limited", "Too many requests."),
}


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or observability_service.new_request_id())


def _payload(request: Request, code: str, message: str, details: list[dict] | None = None) -> dict:
    request_id = _request_id(request)
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "details": details or [],
        },
        "meta": {"request_id": request_id, "timestamp": datetime.now(timezone.utc).isoformat()},
    }


def register_v1_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if not request.url.path.startswith("/api/v1/"):
            return JSONResponse(jsonable_encoder({"detail": exc.errors()}), status_code=422)
        details = [
            {
                "location": list(error.get("loc") or ()),
                "message": str(error.get("msg") or "Invalid value"),
                "type": str(error.get("type") or "validation_error"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            _payload(request, "validation_error", "Request validation failed.", details), status_code=422
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if not request.url.path.startswith("/api/v1/"):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
        code, message = _ERRORS.get(exc.status_code, ("request_failed", "The request could not be completed."))
        # Only a dict detail is a deliberately public envelope written by a route; a string
        # detail is internal wording (auth failures carry credential context) and stays suppressed.
        # HTTPException.detail is declared as str, but routes do raise dict envelopes
        # through it, so the runtime check stays and the declared type is widened here.
        raw_detail: Any = exc.detail
        detail: dict[str, Any] = raw_detail if isinstance(raw_detail, dict) else {}
        code = str(detail.get("code") or code)
        message = str(detail.get("message") or message)
        details = detail.get("field_errors") if isinstance(detail.get("field_errors"), list) else None
        return JSONResponse(_payload(request, code, message, details), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, _exc: Exception):
        if request.url.path.startswith("/api/v1/"):
            return JSONResponse(
                _payload(request, "internal_error", "The request could not be completed."),
                status_code=500,
            )
        return JSONResponse({"detail": "Internal Server Error"}, status_code=500)
