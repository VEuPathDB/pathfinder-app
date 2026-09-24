import logging

import pytest
from assistant_core.platform.types import JSONObject
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from limits import parse
from pydantic import TypeAdapter
from slowapi.errors import RateLimitExceeded
from slowapi.wrappers import Limit
from starlette.requests import Request
from veupathdb.errors import (
    ValidationError,
    VEuPathDBError,
    VEuPathDBErrorCode,
    WDKError,
    WDKLoginRequiredError,
)

from pathfinder.platform.error_handlers import (
    http_exception_handler,
    rate_limit_handler,
    request_validation_handler,
    veupathdb_error_handler,
)
from pathfinder.platform.errors import AppError, ErrorCode

_PROBLEM_JSON = "application/problem+json"


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "server": ("test", 80),
            "path": "/api/v1/x",
            "query_string": b"",
            "headers": [],
        }
    )


def _body(resp: JSONResponse) -> JSONObject:
    return TypeAdapter(JSONObject).validate_json(bytes(resp.body))


def test_an_application_error_is_a_client_refusal() -> None:
    """One hierarchy, so one handler renders both."""
    error = AppError(code=ErrorCode.WDK_ERROR, title="WDK", status=502)
    assert isinstance(error, VEuPathDBError)
    assert error.code is ErrorCode.WDK_ERROR


async def test_the_one_handler_renders_an_application_error() -> None:
    resp = await veupathdb_error_handler(
        _request(),
        AppError(code=ErrorCode.WDK_ERROR, title="WDK", status=502, detail="upstream"),
    )
    assert resp.media_type == _PROBLEM_JSON
    assert resp.status_code == 502
    body = _body(resp)
    assert body["status"] == 502
    assert body["code"] == "WDK_ERROR"
    assert body["detail"] == "upstream"


async def test_the_one_handler_keeps_a_code_only_this_application_names() -> None:
    resp = await veupathdb_error_handler(
        _request(),
        AppError(
            code=ErrorCode.STRATEGY_COMPILATION_ERROR,
            title="Strategy compilation failed",
            status=500,
        ),
    )
    assert resp.status_code == 500
    assert _body(resp)["code"] == "STRATEGY_COMPILATION_ERROR"


async def test_veupathdb_error_handler_keeps_the_code_and_the_status() -> None:
    resp = await veupathdb_error_handler(
        _request(), WDKError("upstream refused", status=502)
    )
    assert resp.media_type == _PROBLEM_JSON
    assert resp.status_code == 502
    body = _body(resp)
    assert body["status"] == 502
    assert body["code"] == "WDK_ERROR"
    assert body["type"] == "/errors/WDK_ERROR"
    assert body["detail"] == "upstream refused"


async def test_veupathdb_error_handler_carries_the_parameter_rows() -> None:
    resp = await veupathdb_error_handler(
        _request(),
        ValidationError(
            title="Invalid parameter value",
            detail="organism is not an option",
            errors=[{"param": "organism", "value": "nope"}],
        ),
    )
    assert resp.status_code == 422
    body = _body(resp)
    assert body["code"] == "VALIDATION_ERROR"
    assert body["errors"] == [{"param": "organism", "value": "nope"}]


async def test_veupathdb_error_handler_renders_a_login_refusal() -> None:
    resp = await veupathdb_error_handler(_request(), WDKLoginRequiredError())
    assert resp.status_code == 401
    assert _body(resp)["code"] == "WDK_LOGIN_REQUIRED"


async def test_every_client_code_is_a_code_the_wire_already_names() -> None:
    for code in VEuPathDBErrorCode:
        resp = await veupathdb_error_handler(
            _request(), VEuPathDBError(code=code, title="x", status=400)
        )
        assert _body(resp)["code"] == code.value
        assert ErrorCode(code.value).value == code.value


async def test_http_exception_handler_returns_problem_json() -> None:
    resp = await http_exception_handler(
        _request(), HTTPException(status_code=404, detail="missing")
    )
    assert resp.media_type == _PROBLEM_JSON
    assert resp.status_code == 404
    assert _body(resp)["code"] == "NOT_FOUND"


async def test_request_validation_handler_returns_problem_json() -> None:
    exc = RequestValidationError(
        [
            {
                "type": "missing",
                "loc": ("query", "x"),
                "msg": "Field required",
                "input": None,
            }
        ]
    )
    resp = await request_validation_handler(_request(), exc)
    assert resp.media_type == _PROBLEM_JSON
    assert resp.status_code == 422
    body = _body(resp)
    assert body["code"] == "VALIDATION_ERROR"
    errors = TypeAdapter(list[JSONObject]).validate_python(body["errors"])
    assert errors[0]["msg"] == "Field required"


async def test_a_value_that_failed_validation_is_neither_logged_nor_echoed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A refused body may be a secret, so the error keeps its place and reason only."""
    secret = "sk-proj-too-short"
    exc = RequestValidationError(
        [
            {
                "type": "string_too_short",
                "loc": ("body", "key"),
                "msg": "String should have at least 20 characters",
                "input": secret,
                "ctx": {"min_length": 20},
            }
        ]
    )

    with caplog.at_level(logging.WARNING):
        resp = await request_validation_handler(_request(), exc)

    assert secret not in bytes(resp.body).decode()
    errors = TypeAdapter(list[JSONObject]).validate_python(_body(resp)["errors"])
    assert errors == [
        {
            "type": "string_too_short",
            "loc": ["body", "key"],
            "msg": "String should have at least 20 characters",
        }
    ]
    logged = " ".join(str(record.msg) for record in caplog.records)
    assert "Request validation failed" in logged
    assert secret not in logged


async def test_rate_limit_handler_returns_problem_json() -> None:
    limit = Limit(
        parse("5/minute"), lambda: "k", "5/minute", False, None, None, None, 1, False
    )
    resp = await rate_limit_handler(_request(), RateLimitExceeded(limit))
    assert resp.media_type == _PROBLEM_JSON
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "60"
    assert _body(resp)["code"] == "RATE_LIMITED"
