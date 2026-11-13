from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy.exc import ProgrammingError
from veupathdb.errors import ValidationError

from strategist.platform.config import get_settings
from strategist.services.audit import job
from strategist.services.audit.runs import create_run, owned_run
from strategist.tests._support.audit import seed_thread
from strategist.tests._support.provider_keys import sealed_provider_keys
from strategist.tests._support.rendered_logs import rendered_logs
from strategist.tests.integration.http.conftest import client_for
from strategist.tests.integration.jobs._audit_jobs import (
    SCOPE,
    TOKEN,
    holding,
    registered,
    wire_checks,
    work_through,
)

_URL = "https://qa.plasmodb.org/plasmo.qa/service/answer?api_key=held-in-the-query"
_SQL = "SELECT token FROM audit_runs WHERE id = 7"
_GENERIC = "An internal error occurred"
_LOG_EVENT = "An audit run stopped on an error"


def _status_error() -> httpx.HTTPStatusError:
    request = httpx.Request("GET", _URL)
    response = httpx.Response(502, request=request)
    return httpx.HTTPStatusError(
        f"Bad gateway for {_URL}", request=request, response=response
    )


def _sql_error() -> ProgrammingError:
    return ProgrammingError(_SQL, {}, Exception("the relation is gone"))


@pytest.fixture
def jobs(
    db_cleaner: None,
    patch_app_db_engine: None,
    site_login_names_the_user: None,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[InMemoryConnector]:
    del db_cleaner, patch_app_db_engine, site_login_names_the_user
    registered(monkeypatch, TOKEN)
    with sealed_provider_keys(monkeypatch), holding(TOKEN):
        yield in_memory_jobs
    get_settings.cache_clear()


async def _fail_with(
    jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    app: FastAPI,
) -> tuple[str | None, httpx.Response]:
    wire_checks(monkeypatch)

    async def crash(*_: object) -> None:
        raise error

    monkeypatch.setattr(job, "_carry_signed_in", crash)
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await job.start_run(run_id, owner)
    with pytest.raises(type(error)):
        await work_through(jobs)
    stored = (await owned_run(run_id, owner)).stages.halted
    async with client_for(app, owner.user_id) as client:
        response = await client.get(f"/api/v1/audits/{run_id}")
    return stored, response


@pytest.mark.parametrize(
    ("error", "kept_out"),
    [(_status_error(), "api_key"), (_sql_error(), "SELECT token")],
)
async def test_a_raw_error_reaches_neither_the_row_nor_the_route(
    jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
    app: FastAPI,
    error: Exception,
    kept_out: str,
) -> None:
    stored, response = await _fail_with(jobs, monkeypatch, error, app)
    reason = f"the audit job failed: {type(error).__name__}: {_GENERIC}"
    assert stored == reason
    assert response.status_code == 200
    body = response.json()
    assert body["halt"] == {"kind": "task_failed", "detail": reason}
    assert body["stages"]["halted"] == reason
    assert kept_out not in response.text


async def test_a_refusal_keeps_its_words(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch, app: FastAPI
) -> None:
    error = ValidationError(title="Search refused", detail="the organism is unknown")
    stored, response = await _fail_with(jobs, monkeypatch, error, app)
    reason = f"the audit job failed: ValidationError: {error}"
    assert "the organism is unknown" in str(error)
    assert stored == reason
    assert response.json()["halt"]["detail"] == reason


async def test_the_full_error_stays_in_the_log_with_the_run_bound(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch, app: FastAPI
) -> None:
    with rendered_logs() as logs:
        await _fail_with(jobs, monkeypatch, _status_error(), app)
    line = logs.line(_LOG_EVENT)
    assert line["run_id"]
    assert "api_key=held-in-the-query" in str(line["exception"])
