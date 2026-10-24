"""A run's page resumes it when it stopped and retries what it left unread when it finished,
and refuses every other start."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from uuid import UUID

import pytest
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector

from pathfinder.platform.config import get_settings
from pathfinder.services import wdk_identity
from pathfinder.services.audit import page_start
from pathfinder.services.audit.reviews import defer_review
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.http._audit_reads import (
    delete_conversation,
    finished_run_with_an_unread_finding,
    halted_run,
)
from pathfinder.tests.integration.http.conftest import client_for
from pathfinder.tests.integration.jobs._audit_jobs import TOKEN, queued, registered

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "site_login_names_the_user"
)


@pytest.fixture
def jobs(
    in_memory_jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> Iterator[InMemoryConnector]:
    registered(monkeypatch, TOKEN)
    with sealed_provider_keys(monkeypatch):
        yield in_memory_jobs
    get_settings.cache_clear()


@pytest.fixture
def sign_in(monkeypatch: pytest.MonkeyPatch) -> Callable[[UUID], None]:
    def _as(user_id: UUID) -> None:
        async def _resolved(token: str, site_id: str) -> UUID:
            del token, site_id
            return user_id

        monkeypatch.setattr(wdk_identity, "resolve_veupathdb_user_id", _resolved)

    return _as


async def _always_working(run_id: UUID) -> bool:
    del run_id
    return True


def _waiting(connector: InMemoryConnector) -> list[str]:
    return [j["task_name"] for j in connector.jobs.values() if j["status"] == "todo"]


def _queued_runs(connector: InMemoryConnector) -> list[str]:
    return [job["args"]["payload"]["run_id"] for job in queued(connector)]


async def test_a_stopped_run_resumes_from_the_page(
    app: FastAPI, jobs: InMemoryConnector, sign_in: Callable[[UUID], None]
) -> None:
    owner, run_id = await halted_run()
    sign_in(owner.user_id)
    async with client_for(app, owner.user_id, wdk_token=TOKEN) as client:
        started = await client.post(
            f"/api/v1/audits/{run_id}/start", json={"action": "resume"}
        )
    body = started.json()
    assert started.status_code == 200
    assert (body["run"]["phase"], body["action"], body["halt"]) == (
        "running",
        None,
        None,
    )
    assert _queued_runs(jobs) == [str(run_id)]


async def test_a_finished_run_retries_what_it_left_unread(
    app: FastAPI, jobs: InMemoryConnector, sign_in: Callable[[UUID], None]
) -> None:
    owner, run_id = await finished_run_with_an_unread_finding()
    sign_in(owner.user_id)
    async with client_for(app, owner.user_id, wdk_token=TOKEN) as client:
        before = (await client.get(f"/api/v1/audits/{run_id}")).json()
        started = await client.post(
            f"/api/v1/audits/{run_id}/start", json={"action": "retry"}
        )
    body = started.json()
    assert (before["action"], before["left"]["total"]) == ("retry", 1)
    assert started.status_code == 200
    assert (body["run"]["phase"], body["left"]["total"], body["action"]) == (
        "running",
        0,
        None,
    )
    assert _queued_runs(jobs) == [str(run_id)]


async def test_a_start_while_reviews_hold_the_lock_is_refused(
    app: FastAPI, jobs: InMemoryConnector, sign_in: Callable[[UUID], None]
) -> None:
    owner, run_id = await finished_run_with_an_unread_finding()
    sign_in(owner.user_id)
    await defer_review(run_id)
    async with client_for(app, owner.user_id, wdk_token=TOKEN) as client:
        retried = await client.post(
            f"/api/v1/audits/{run_id}/start", json={"action": "retry"}
        )
        run = (await client.get(f"/api/v1/audits/{run_id}")).json()
    assert (retried.status_code, retried.json()["code"]) == (409, "AUDIT_NOT_STARTABLE")
    assert retried.json()["detail"] == (
        "this run's reviews are running; start it again when they finish"
    )
    assert (run["run"]["phase"], run["action"], run["reviewsRunning"]) == (
        "finished",
        None,
        True,
    )
    assert run["left"]["total"] == 1
    assert _waiting(jobs) == ["audit:review"]


async def test_a_start_while_another_task_of_the_run_is_queued_is_refused(
    app: FastAPI,
    jobs: InMemoryConnector,
    sign_in: Callable[[UUID], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, run_id = await halted_run()
    sign_in(owner.user_id)
    monkeypatch.setattr(page_start, "working", _always_working)
    async with client_for(app, owner.user_id, wdk_token=TOKEN) as client:
        resumed = await client.post(
            f"/api/v1/audits/{run_id}/start", json={"action": "resume"}
        )
        run = (await client.get(f"/api/v1/audits/{run_id}")).json()
    assert (resumed.status_code, resumed.json()["code"]) == (409, "AUDIT_NOT_STARTABLE")
    assert resumed.json()["detail"] == "a task of this run is already queued or running"
    assert (run["run"]["phase"], run["action"]) == ("halted", "resume")
    assert _waiting(jobs) == []


async def test_an_action_the_run_does_not_offer_is_refused(
    app: FastAPI, jobs: InMemoryConnector, sign_in: Callable[[UUID], None]
) -> None:
    owner, run_id = await finished_run_with_an_unread_finding()
    sign_in(owner.user_id)
    halted_owner, halted_id = await halted_run()
    async with client_for(app, owner.user_id, wdk_token=TOKEN) as client:
        resumed = await client.post(
            f"/api/v1/audits/{run_id}/start", json={"action": "resume"}
        )
    sign_in(halted_owner.user_id)
    async with client_for(app, halted_owner.user_id, wdk_token=TOKEN) as client:
        retried = await client.post(
            f"/api/v1/audits/{halted_id}/start", json={"action": "retry"}
        )
    assert (resumed.status_code, resumed.json()["code"]) == (409, "AUDIT_NOT_STARTABLE")
    assert resumed.json()["detail"] == "this run offers a retry, not a resume"
    assert (retried.status_code, retried.json()["detail"]) == (
        409,
        "this run offers a resume, not a retry",
    )
    assert _waiting(jobs) == []


async def test_a_run_that_offers_no_action_is_not_started_again(
    app: FastAPI, jobs: InMemoryConnector, sign_in: Callable[[UUID], None]
) -> None:
    owner, run_id = await halted_run()
    sign_in(owner.user_id)
    async with client_for(app, owner.user_id, wdk_token=TOKEN) as client:
        first = await client.post(
            f"/api/v1/audits/{run_id}/start", json={"action": "resume"}
        )
        again = await client.post(
            f"/api/v1/audits/{run_id}/start", json={"action": "resume"}
        )
    assert first.status_code == 200
    assert (again.status_code, again.json()["detail"]) == (
        409,
        "this run offers no start now",
    )
    assert _queued_runs(jobs) == [str(run_id)]


async def test_a_run_whose_conversation_was_deleted_is_not_started(
    app: FastAPI, jobs: InMemoryConnector, sign_in: Callable[[UUID], None]
) -> None:
    owner, run_id = await halted_run()
    sign_in(owner.user_id)
    await delete_conversation(owner.conversation_id)
    async with client_for(app, owner.user_id, wdk_token=TOKEN) as client:
        resumed = await client.post(
            f"/api/v1/audits/{run_id}/start", json={"action": "resume"}
        )
    assert (resumed.status_code, resumed.json()["code"]) == (409, "AUDIT_NOT_STARTABLE")
    assert resumed.json()["detail"] == (
        "the conversation that started this run was deleted"
    )
    assert _waiting(jobs) == []


async def test_a_start_names_one_of_the_two_actions_and_nothing_else(
    app: FastAPI, jobs: InMemoryConnector, sign_in: Callable[[UUID], None]
) -> None:
    owner, run_id = await halted_run()
    sign_in(owner.user_id)
    async with client_for(app, owner.user_id, wdk_token=TOKEN) as client:
        restarted = await client.post(
            f"/api/v1/audits/{run_id}/start", json={"action": "restart"}
        )
        forced = await client.post(
            f"/api/v1/audits/{run_id}/start",
            json={"action": "resume", "force": True},
        )
    assert (restarted.status_code, forced.status_code) == (422, 422)
    assert _waiting(jobs) == []


async def test_a_sign_in_that_names_another_account_is_refused(
    app: FastAPI, jobs: InMemoryConnector, sign_in: Callable[[UUID], None]
) -> None:
    owner, run_id = await halted_run()
    stranger = await seed_thread()
    sign_in(stranger.user_id)
    async with client_for(app, owner.user_id, wdk_token=TOKEN) as client:
        resumed = await client.post(
            f"/api/v1/audits/{run_id}/start", json={"action": "resume"}
        )
        run = (await client.get(f"/api/v1/audits/{run_id}")).json()
    assert (resumed.status_code, resumed.json()["code"]) == (
        401,
        "WDK_IDENTITY_MISMATCH",
    )
    assert (run["run"]["phase"], run["action"]) == ("halted", "resume")
    assert _waiting(jobs) == []


async def test_another_persons_run_is_not_found_and_no_sign_in_is_refused(
    app: FastAPI, jobs: InMemoryConnector, sign_in: Callable[[UUID], None]
) -> None:
    owner, run_id = await halted_run()
    stranger = await seed_thread()
    sign_in(stranger.user_id)
    async with client_for(app, stranger.user_id, wdk_token=TOKEN) as client:
        theirs = await client.post(
            f"/api/v1/audits/{run_id}/start", json={"action": "resume"}
        )
    async with client_for(app, owner.user_id) as client:
        unsigned = await client.post(
            f"/api/v1/audits/{run_id}/start", json={"action": "resume"}
        )
    assert theirs.status_code == 404
    assert (unsigned.status_code, unsigned.json()["code"]) == (
        401,
        "WDK_LOGIN_REQUIRED",
    )
    assert _waiting(jobs) == []
