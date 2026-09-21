"""Error envelope and exception -> HTTP status mapping (docs/16)."""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.errors import DomainError
from app.schemas import ToolErrorCode

logger = logging.getLogger(__name__)

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

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        """Anything not modelled as a DomainError.

        Without this, an unmodelled bug (an AttributeError, a None where a
        row was assumed) fell through to Starlette's default handler and
        returned plain-text "Internal Server Error": a fourth error shape,
        not JSON, with no `retryable` and -- the part that matters -- no
        `correlation_id`. The envelope exists so a user can quote an id and
        someone can find the failure in the log; an untyped crash was the
        one case where that broke down, which is exactly when you need it.

        The message is deliberately generic: an exception string can carry a
        query fragment or a file path, and this body reaches the browser.
        The detail goes to the log, tied to the same id.
        """
        correlation_id = str(uuid.uuid4())
        logger.exception(
            "unhandled error on %s %s (correlation_id=%s)",
            request.method, request.url.path, correlation_id,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Something went wrong handling this request.",
                    "retryable": True,
                    "correlation_id": correlation_id,
                }
            },
        )
