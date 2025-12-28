from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str, detail: str | None = None) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)


class MissingGarminAuth(Exception):
    pass


class GarminAuthFailure(Exception):
    pass


class UpstreamTimeout(Exception):
    pass


def _payload(code: str, message: str, detail: str | None) -> dict[str, Any]:
    return ErrorResponse(error=ErrorDetail(code=code, message=message, detail=detail)).model_dump()


def api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_payload(exc.code, exc.message, exc.detail),
    )


def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else None
    return JSONResponse(
        status_code=exc.status_code,
        content=_payload("http_error", "Request failed", detail),
    )


def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=_payload("invalid_request", "Invalid request", str(exc)),
    )


def missing_auth_handler(_: Request, exc: MissingGarminAuth) -> JSONResponse:
    detail = str(exc) if str(exc) else None
    return JSONResponse(
        status_code=503,
        content=_payload("needs_login", "Garmin authentication required", detail),
    )


def garmin_auth_failure_handler(_: Request, exc: GarminAuthFailure) -> JSONResponse:
    detail = str(exc) if str(exc) else None
    return JSONResponse(
        status_code=502,
        content=_payload("garmin_auth_failure", "Garmin authentication failed", detail),
    )


def upstream_timeout_handler(_: Request, exc: UpstreamTimeout) -> JSONResponse:
    detail = str(exc) if str(exc) else None
    return JSONResponse(
        status_code=504,
        content=_payload("upstream_timeout", "Garmin request timed out", detail),
    )


def register_exception_handlers(app: Any) -> None:
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(MissingGarminAuth, missing_auth_handler)
    app.add_exception_handler(GarminAuthFailure, garmin_auth_failure_handler)
    app.add_exception_handler(UpstreamTimeout, upstream_timeout_handler)
