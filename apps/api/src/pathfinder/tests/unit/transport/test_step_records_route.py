"""The route that answers one page of the genes a strategy step returns."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
from assistant_core.platform.db import get_db_session
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.errors import VEuPathDBError

from pathfinder.platform.error_handlers import (
    request_validation_handler,
    veupathdb_error_handler,
)
from pathfinder.services.conversations import step_records
from pathfinder.tests._support.step_answers import (
    PUSHED_STEP,
    SITE,
    UNPUSHED_STEP,
    SiteApi,
    thread,
)
from pathfinder.transport.http.deps import get_current_user_with_db_row
from pathfinder.transport.http.routers.conversations.step_records import router

_Handler = Callable[[Request, Exception], Awaitable[Response]]


def _app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    stored = thread()
    api = SiteApi()

    async def _owned(*_args: Any, **_kwargs: Any) -> Any:
        return stored

    async def _session() -> AsyncGenerator[AsyncSession]:
        yield AsyncSession()

    async def _user() -> Any:
        return stored[0].user_id

    monkeypatch.setattr(step_records, "get_owned_thread", _owned)
    monkeypatch.setattr(step_records, "get_strategy_api", lambda _site_id: api)
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(VEuPathDBError, cast("_Handler", veupathdb_error_handler))
    app.add_exception_handler(
        RequestValidationError, cast("_Handler", request_validation_handler)
    )
    app.dependency_overrides[get_db_session] = _session
    app.dependency_overrides[get_current_user_with_db_row] = _user
    return app


async def _get(
    monkeypatch: pytest.MonkeyPatch, step_id: str, **params: str | int
) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app(monkeypatch))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(
            f"/api/v1/conversations/{uuid4()}/strategy/steps/{step_id}/records",
            params={"siteId": SITE, **params},
        )


async def test_a_pushed_step_answers_its_page_of_genes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = await _get(monkeypatch, PUSHED_STEP, offset=0, limit=2)

    assert response.status_code == 200
    assert response.json() == {
        "stepId": "step_exons",
        "wdkStepId": 11,
        "total": 6414,
        "offset": 0,
        "limit": 2,
        "recordType": "transcript",
        "stepUrl": "https://toxodb.org/toxo/app/workspace/strategies/900/11",
        "records": [
            {
                "geneId": "TGME49_200010",
                "organism": "Toxoplasma gondii ME49",
                "product": "dense granule protein GRA20",
                "recordUrl": "https://toxodb.org/toxo/app/record/gene/TGME49_200010",
            },
            {
                "geneId": "TGME49_200130",
                "organism": "Toxoplasma gondii ME49",
                "product": "Toxoplasma gondii family C protein",
                "recordUrl": "https://toxodb.org/toxo/app/record/gene/TGME49_200130",
            },
        ],
    }


async def test_a_step_not_on_the_site_answers_a_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = await _get(monkeypatch, UNPUSHED_STEP)

    assert response.status_code == 409
    assert (response.json()["code"], response.json()["detail"]) == (
        "INVALID_STRATEGY",
        f"Step {UNPUSHED_STEP!r} is not on the site yet, so it has no results.",
    )


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 501}, {"offset": -1}], ids=str
)
async def test_a_page_outside_the_bounds_is_refused(
    monkeypatch: pytest.MonkeyPatch, params: dict[str, int]
) -> None:
    response = await _get(monkeypatch, PUSHED_STEP, **params)

    assert response.status_code == 422
