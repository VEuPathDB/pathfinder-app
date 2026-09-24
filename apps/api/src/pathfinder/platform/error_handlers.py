"""FastAPI exception handlers that render every error as problem+json."""

from enum import StrEnum
from http import HTTPStatus

import structlog
from assistant_core import registry
from assistant_core.errors import (
    AssistantCoreError,
    ConversationForbiddenError,
    ConversationNotFoundError,
    TurnStillRunningError,
)
from assistant_core.platform.types import JSONArray
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, TypeAdapter
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException
from veupathdb.errors import VEuPathDBError

from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.platform.errors import (
    AssistantMismatchError,
    AssistantNotFoundError,
    ErrorCode,
    ProblemDetail,
)

_logger = structlog.get_logger(__name__)

# The runtime raises without a transport, so this application names the status
# and the code each of its refusals answers with.
_RUNTIME_REFUSALS: dict[type[AssistantCoreError], tuple[int, ErrorCode, str]] = {
    ConversationNotFoundError: (
        HTTPStatus.NOT_FOUND,
        ErrorCode.STRATEGY_NOT_FOUND,
        "Conversation not found",
    ),
    ConversationForbiddenError: (
        HTTPStatus.FORBIDDEN,
        ErrorCode.FORBIDDEN,
        "Forbidden",
    ),
    TurnStillRunningError: (
        HTTPStatus.CONFLICT,
        ErrorCode.SESSION_CONFLICT,
        "A turn is still running",
    ),
}

# The handler is registered for each mapped type, so a refusal the map does not
# name is not answered here at all.
RUNTIME_REFUSALS: tuple[type[AssistantCoreError], ...] = tuple(_RUNTIME_REFUSALS)

_STATUS_TO_ERROR_CODE: dict[int, ErrorCode] = {
    HTTPStatus.NOT_FOUND: ErrorCode.NOT_FOUND,
    HTTPStatus.UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
    HTTPStatus.FORBIDDEN: ErrorCode.FORBIDDEN,
    HTTPStatus.TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
}


def problem_response(
    request: Request,
    *,
    status: int,
    code: ErrorCode,
    title: str,
    detail: str | None = None,
    errors: JSONArray | None = None,
) -> JSONResponse:
    """Render a single ProblemDetail (RFC 9457) as application/problem+json."""
    problem = ProblemDetail(
        type=f"/errors/{code.value}",
        title=title,
        status=status,
        detail=detail,
        instance=str(request.url),
        code=code,
        errors=errors,
    )
    return JSONResponse(
        status_code=status,
        content=problem.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


def _failed(
    request: Request, exc: VEuPathDBError[StrEnum], code: ErrorCode
) -> JSONResponse:
    log = _logger.bind(
        method=request.method,
        path=request.url.path,
        status=exc.status,
        code=code.value,
        title=exc.title,
        detail=exc.detail,
        errors=exc.errors,
    )
    if exc.status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        log.error("Request failed", exc_info=exc)
    else:
        log.warning("Request failed")
    return problem_response(
        request,
        status=exc.status,
        code=code,
        title=exc.title,
        detail=exc.detail,
        errors=exc.errors,
    )


async def veupathdb_error_handler(
    request: Request, exc: VEuPathDBError[StrEnum]
) -> JSONResponse:
    """Render any refusal under the code the wire already names."""
    return _failed(request, exc, ErrorCode(exc.code.value))


async def assistant_core_error_handler(
    request: Request, exc: AssistantCoreError
) -> JSONResponse:
    """Render a runtime refusal under the status this application gives it."""
    status, code, title = _RUNTIME_REFUSALS[type(exc)]
    _logger.warning(
        "Request failed",
        method=request.method,
        path=request.url.path,
        status=status,
        code=code.value,
        title=title,
    )
    return problem_response(
        request,
        status=status,
        code=code,
        title=title,
        detail=str(exc),
    )


async def unknown_assistant_handler(
    request: Request, exc: registry.UnknownAssistantError
) -> JSONResponse:
    """Render an assistant id this deployment does not serve."""
    refusal = AssistantNotFoundError(exc.assistant_id, exc.known)
    return _failed(request, refusal, ErrorCode(refusal.code.value))


async def assistant_mismatch_handler(
    request: Request, exc: registry.AssistantMismatchError
) -> JSONResponse:
    """Render a request that names an assistant other than its thread's."""
    refusal = AssistantMismatchError(requested=exc.requested, existing=exc.existing)
    return _failed(request, refusal, ErrorCode(refusal.code.value))


async def apply_error_handler(request: Request, exc: ApplyError) -> JSONResponse:
    """Render an operation the graph rejected. The op algebra names the cause."""
    _logger.warning(
        "Graph operation rejected",
        method=request.method,
        path=request.url.path,
        detail=str(exc),
    )
    return problem_response(
        request,
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
        code=ErrorCode.VALIDATION_ERROR,
        title="Operation rejected",
        detail=str(exc),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTPException."""
    code = _STATUS_TO_ERROR_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    return problem_response(
        request,
        status=exc.status_code,
        code=code,
        title=str(exc.detail),
    )


class _FieldError(BaseModel):
    """Where a request failed validation and why, without the value it held.

    A refused value may be a secret, so neither the log nor the answer carries it.
    """

    model_config = ConfigDict(extra="ignore")

    type: str
    loc: tuple[int | str, ...]
    msg: str


_FIELD_ERRORS = TypeAdapter(list[_FieldError])


async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle request validation errors as problem+json with field-level errors."""
    reported = _FIELD_ERRORS.validate_python(exc.errors())
    errors = jsonable_encoder([error.model_dump() for error in reported])
    _logger.warning(
        "Request validation failed",
        method=request.method,
        path=request.url.path,
        errors=errors,
    )
    summary = "; ".join(error.msg for error in reported) or "Request validation failed"
    return problem_response(
        request,
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
        code=ErrorCode.VALIDATION_ERROR,
        title="Request validation failed",
        detail=summary,
        errors=errors,
    )


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Handle slowapi rate-limit rejections as problem+json."""
    response = problem_response(
        request,
        status=HTTPStatus.TOO_MANY_REQUESTS,
        code=ErrorCode.RATE_LIMITED,
        title="Rate limit exceeded",
        detail=str(exc.detail),
    )
    response.headers["Retry-After"] = "60"
    return response
