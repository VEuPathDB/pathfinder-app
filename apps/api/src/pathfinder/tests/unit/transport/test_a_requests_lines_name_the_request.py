from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, FastAPI

from pathfinder.platform.route_templates import install_route_templates
from pathfinder.platform.security import create_user_token, get_current_user
from pathfinder.tests._support.rendered_logs import rendered_logs

_KEYS = ("request_id", "method", "route", "user_id", "conversation_id")
_BOUND = {"method", "route", "user_id", "conversation_id"}
_THREAD_ROUTE = "/api/v1/conversations/{conversation_id}/log-probe"


async def _thread_probe(
    conversation_id: UUID, user_id: Annotated[UUID, Depends(get_current_user)]
) -> None:
    del conversation_id, user_id
    logging.getLogger("httpx").warning("thread request line")


async def _open_probe() -> None:
    logging.getLogger("httpx").warning("open request line")


async def test_a_requests_lines_name_the_request_the_route_and_the_user(
    app: FastAPI,
) -> None:
    app.add_api_route(_THREAD_ROUTE, _thread_probe, methods=["GET"])
    app.add_api_route("/api/v1/log-probe", _open_probe, methods=["GET"])
    install_route_templates(app)
    user_id, conversation_id = uuid4(), uuid4()
    bearer = {"Authorization": f"Bearer {create_user_token(user_id)}"}

    with rendered_logs() as logs:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread = await client.get(
                f"/api/v1/conversations/{conversation_id}/log-probe?siteId=plasmodb",
                headers={**bearer, "X-Request-ID": "request-one"},
            )
            opened = await client.get(
                "/api/v1/log-probe", headers={"X-Request-ID": "request-two"}
            )
            unread = await client.get(
                "/api/v1/conversations/not-an-id/log-probe", headers=bearer
            )
            carried = await client.get(
                "/api/v1/log-probe", headers={"X-Request-ID": "a@b.org"}
            )
        logging.getLogger("httpx").warning("after the requests")

    assert (thread.status_code, opened.status_code, unread.status_code) == (
        200,
        200,
        422,
    )
    line = logs.line("thread request line")
    assert {key: line[key] for key in _KEYS} == {
        "request_id": "request-one",
        "method": "GET",
        "route": _THREAD_ROUTE,
        "user_id": str(user_id),
        "conversation_id": str(conversation_id),
    }
    second, third = [
        line for line in logs.lines() if line["event"] == "open request line"
    ]
    assert {key: second[key] for key in ("request_id", "method", "route")} == {
        "request_id": "request-two",
        "method": "GET",
        "route": "/api/v1/log-probe",
    }
    assert {"user_id", "conversation_id"} & set(second) == set()
    assert _BOUND & set(logs.line("after the requests")) == set()
    minted = carried.headers["X-Request-ID"]
    assert minted != "a@b.org"
    assert UUID(minted).version == 4
    assert third["request_id"] == minted


async def _strategy_probe(strategyId: UUID) -> None:
    del strategyId
    logging.getLogger("httpx").warning("strategy request line")


async def test_a_thread_named_strategy_id_under_an_include_prefix_is_named(
    app: FastAPI,
) -> None:
    probes = APIRouter()
    probes.add_api_route("/{strategyId:uuid}/log-probe", _strategy_probe)
    nested = APIRouter()
    nested.include_router(probes, prefix="/api/v1/probe-threads")
    app.include_router(nested)
    install_route_templates(app)
    conversation_id = uuid4()

    with rendered_logs() as logs:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            answered = await client.get(
                f"/api/v1/probe-threads/{conversation_id}/log-probe"
            )

    assert answered.status_code == 200
    line = logs.line("strategy request line")
    assert (line["route"], line["conversation_id"]) == (
        "/api/v1/probe-threads/{strategyId}/log-probe",
        str(conversation_id),
    )
