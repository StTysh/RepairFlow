"""Domain exceptions, mapped to ToolErrorCode at the API/executor boundary."""
from __future__ import annotations

from app.schemas import ToolErrorCode


class DomainError(Exception):
    code: ToolErrorCode = ToolErrorCode.VALIDATION_ERROR
    retryable: bool = False
    reconciliation_required: bool = False

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    code = ToolErrorCode.NOT_FOUND


class ForbiddenError(DomainError):
    code = ToolErrorCode.FORBIDDEN


class StaleVersionError(DomainError):
    code = ToolErrorCode.STALE_VERSION

    def __init__(self, message: str, current_version: int):
        super().__init__(message)
        self.current_version = current_version


class PolicyRejectedError(DomainError):
    code = ToolErrorCode.POLICY_REJECTED


class ApprovalRequiredError(DomainError):
    code = ToolErrorCode.APPROVAL_REQUIRED


class PayloadTooLargeError(DomainError):
    """An upload exceeded the configured size cap. Distinct from a
    validation error so the client sees a true 413 and can tell
    "this file is too big" from "this field is wrong"."""

    code = ToolErrorCode.PAYLOAD_TOO_LARGE


class ConflictError(DomainError):
    code = ToolErrorCode.CONFLICT


class ExternalResultUnknownError(DomainError):
    code = ToolErrorCode.EXTERNAL_RESULT_UNKNOWN
    retryable = False
    reconciliation_required = True


class ProviderUnavailableError(DomainError):
    """Raised when a live provider path is invoked without credentials
    configured -- e.g. voice session creation when elevenlabs_live is
    False. Never fabricate a session/result instead of raising this."""

    code = ToolErrorCode.PROVIDER_UNAVAILABLE
    retryable = True
