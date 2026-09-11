"""The runtime raises without a status; this application supplies one."""

from uuid import UUID

from assistant_core.errors import (
    AssistantCoreError,
    ConversationForbiddenError,
    ConversationNotFoundError,
    TurnStillRunningError,
)
from assistant_core.platform.types import JSONObject
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter
from starlette.requests import Request

from pathfinder.platform.error_handlers import (
    RUNTIME_REFUSALS,
    assistant_core_error_handler,
)

_PROBLEM_JSON = "application/problem+json"
_CONVERSATION_ID = UUID("11111111-1111-1111-1111-111111111111")


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


async def test_a_thread_the_caller_cannot_see_reads_as_not_found() -> None:
    resp = await assistant_core_error_handler(
        _request(), ConversationNotFoundError(_CONVERSATION_ID)
    )
    assert resp.status_code == 404
    assert resp.media_type == _PROBLEM_JSON
    assert _body(resp)["code"] == "STRATEGY_NOT_FOUND"


async def test_a_thread_of_another_caller_is_forbidden() -> None:
    resp = await assistant_core_error_handler(
        _request(), ConversationForbiddenError(_CONVERSATION_ID)
    )
    assert resp.status_code == 403
    assert _body(resp)["code"] == "FORBIDDEN"


async def test_a_turn_still_in_flight_is_a_conflict() -> None:
    resp = await assistant_core_error_handler(
        _request(), TurnStillRunningError(_CONVERSATION_ID)
    )
    assert resp.status_code == 409
    assert _body(resp)["code"] == "SESSION_CONFLICT"
    assert str(_CONVERSATION_ID) in str(_body(resp)["detail"])


def test_every_refusal_the_runtime_raises_has_a_status_here() -> None:
    """A release that adds a refusal fails here rather than at a route."""
    assert set(RUNTIME_REFUSALS) == set(AssistantCoreError.__subclasses__())
