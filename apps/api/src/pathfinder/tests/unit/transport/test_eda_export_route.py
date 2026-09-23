"""The tab's export route refuses a subset that selects no gene with a 422."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
from assistant_core.platform.db import get_db_session
from fastapi import FastAPI, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.eda import EdaAnalysisDetail
from veupathdb.errors import VEuPathDBError

from pathfinder.platform.error_handlers import veupathdb_error_handler
from pathfinder.services.eda import gene_subset, steps
from pathfinder.tests.unit.ai.tools._eda_step_doubles import (
    SAMPLE_ONLY_REFUSAL,
    analysis_detail,
    bound,
    de_study,
    sample_filter,
)
from pathfinder.transport.http.deps import get_current_user_with_db_row
from pathfinder.transport.http.routers import eda

_Handler = Callable[[Request, Exception], Awaitable[Response]]


def _app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    async def _owner(*_args: object) -> None:
        return None

    async def _opened(*, conversation_id: object) -> tuple[Any, EdaAnalysisDetail]:
        del conversation_id
        detail = analysis_detail(with_computation=False, filters=[sample_filter()])
        return await bound(None), detail

    async def _session() -> AsyncGenerator[AsyncSession]:
        yield AsyncSession()

    async def _user() -> Any:
        return uuid4()

    monkeypatch.setattr(eda, "assert_owner", _owner)
    monkeypatch.setattr(steps, "open_analysis_or_conflict", _opened)
    monkeypatch.setattr(gene_subset, "get_study_detail_for_dataset", de_study)
    app = FastAPI()
    app.include_router(eda.conversation_router)
    app.add_exception_handler(VEuPathDBError, cast("_Handler", veupathdb_error_handler))
    app.dependency_overrides[get_db_session] = _session
    app.dependency_overrides[get_current_user_with_db_row] = _user
    return app


async def test_a_sample_subset_export_answers_the_422_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.ASGITransport(app=_app(monkeypatch))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/conversations/{uuid4()}/eda",
            json={"action": "export-step", "thresholds": None},
        )

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["title"] == "The subset selects no genes"
    assert body["status"] == 422
    assert body["detail"] == SAMPLE_ONLY_REFUSAL
