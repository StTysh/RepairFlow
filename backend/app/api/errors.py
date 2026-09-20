"""Error envelope and exception -> HTTP status mapping (docs/16)."""
from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.errors import DomainError
from app.schemas import ToolErrorCode

_STATUS_BY_CODE: dict[ToolErrorCode, int] = {
    ToolErrorCode.VALIDATION_ERROR: 422,
    ToolErrorCode.NOT_FOUND: 404,
    ToolErrorCode.FORBIDDEN: 403,
    ToolErrorCode.STALE_VERSION: 409,
    ToolErrorCode.POLICY_REJECTED: 422,
    ToolErrorCode.APPROVAL_REQUIRED: 409,
    ToolErrorCode.CONFLICT: 409,
    ToolErrorCode.RATE_LIMITED: 429,
    ToolErrorCode.PROVIDER_UNAVAILABLE: 503,
    ToolErrorCode.EXTERNAL_RESULT_UNKNOWN: 202,
    ToolErrorCode.PAYLOAD_TOO_LARGE: 413,
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        correlation_id = str(uuid.uuid4())
        status_code = _STATUS_BY_CODE.get(exc.code, 400)
        body = {
            "error": {
                "code": exc.code.value, "message": exc.message,
                "retryable": exc.retryable, "correlation_id": correlation_id,
            }
        }
        if hasattr(exc, "current_version"):
            body["error"]["current_version"] = exc.current_version  # type: ignore[attr-defined]
        return JSONResponse(status_code=status_code, content=body)
