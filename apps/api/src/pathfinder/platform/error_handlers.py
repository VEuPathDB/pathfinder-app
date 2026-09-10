"""FastAPI exception handlers that render every error as problem+json."""

from enum import StrEnum
from http import HTTPStatus

import structlog
from assistant_core.platform.types import JSONArray
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException
from veupathdb.domain.strategy.operations.apply import ApplyError
from veupathdb.errors import VEuPathDBError

from pathfinder.platform.errors import ErrorCode, ProblemDetail

_logger = structlog.get_logger(__name__)

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


async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle request validation errors as problem+json with field-level errors."""
    raw = exc.errors()
    _logger.warning(
        "Request validation failed",
        method=request.method,
        path=request.url.path,
        errors=raw,
    )
    summary = "; ".join(item["msg"] for item in raw) or "Request validation failed"
    return problem_response(
        request,
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
        code=ErrorCode.VALIDATION_ERROR,
        title="Request validation failed",
        detail=summary,
        errors=jsonable_encoder(raw),
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
