"""Every mutating route over an owned resource refuses a non-owner.

The matrix is cross-checked against ``app.routes``, so a new route cannot join
the app without joining it. Each case runs twice: the non-owner must be
refused and the owner must not, which is what makes the refusal ownership.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.memory.store import MemoryStore
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.platform.config import get_settings
from pathfinder.tests.integration.http._authz_matrix_cases import cases
from pathfinder.tests.integration.http._authz_matrix_owned import (
    create_owned,
    placeholder_owned,
)
from pathfinder.tests.integration.http._authz_matrix_support import (
    GENE_SET,
    NO_OWNER_CONTRAST,
    OWNER_REFUSAL_STATUSES,
    REFUSAL_STATUSES,
    RESOURCES,
    Owned,
    Resource,
    registered_routes,
    scoped_routes,
    stale_exclusions,
    status_for,
)
from pathfinder.tests.integration.http.conftest import (
    client_for,
    ends_at_first_frame,
    make_user,
    other_application_client_for,
)

_BLUEPRINTS = cases(placeholder_owned())


@pytest.fixture(scope="module", autouse=True)
async def _langgraph_checkpoint_tables(
    patch_app_db_engine: None,
) -> AsyncGenerator[None]:
    """Fork and revert write checkpoints, which the test transport never creates."""
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url):
        yield


@pytest.fixture
async def owned(
    db_session: AsyncSession,
    app_memory_store: MemoryStore,
    signed_in_to_veupathdb: None,
) -> Owned:
    """One instance of every owned resource kind, held by a fresh user."""
    del signed_in_to_veupathdb
    return await create_owned(db_session, app_memory_store)


class _NestedTarget(BaseModel):
    gene_set_id: str


class _NestedBody(BaseModel):
    """A resource id one model down, behind a list and an optional."""

    targets: list[_NestedTarget] | None = None


def test_every_case_names_a_route_the_app_still_serves(app: FastAPI) -> None:
    registered = registered_routes(app)
    missing = [
        (case.method, case.route)
        for case in _BLUEPRINTS
        if (case.method, case.route) not in registered
    ]
    assert missing == [], (
        f"authz matrix names routes the app no longer serves: {missing}"
    )


def test_every_exclusion_names_a_route_the_matrix_would_otherwise_demand(
    app: FastAPI,
) -> None:
    """A stale exclusion is a silent coverage hole, so each one must still bite."""
    stale = stale_exclusions(app)
    covered = {(case.method, case.route) for case in _BLUEPRINTS}
    stale += [
        f"{method} {route} ({waiver.reason})"
        for (method, route), waiver in NO_OWNER_CONTRAST.items()
        if (method, route) not in covered
    ]
    assert stale == [], f"authz matrix exclusions that name nothing: {stale}"


def test_a_resource_id_behind_a_list_and_an_optional_is_still_classified() -> None:
    """Classification reaches a model through any nesting of generics."""
    probe = FastAPI()

    @probe.post("/api/v1/probe")
    async def _endpoint(body: _NestedBody) -> None:
        del body

    assert scoped_routes(probe, GENE_SET) == {("POST", "/api/v1/probe")}


@pytest.mark.parametrize("resource", RESOURCES, ids=lambda r: r.name)
def test_every_scoped_mutating_route_is_in_the_matrix(
    app: FastAPI,
    resource: Resource,
) -> None:
    covered = {
        (case.method, case.route)
        for case in _BLUEPRINTS
        if resource.name in case.resources
    }
    uncovered = sorted(scoped_routes(app, resource) - covered)
    assert uncovered == [], (
        f"{resource.name}-scoped mutating routes missing from the authz matrix: "
        f"{uncovered}"
    )


async def test_begin_refuses_a_non_owner_with_a_stable_problem_code(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    owned: Owned,
) -> None:
    """Pins the refusal the begin route surfaces, wherever it is raised."""
    del patch_app_db_engine
    intruder = await make_user(db_session)

    async with client_for(app, intruder.id) as client:
        response = await client.post(
            f"/api/v1/conversations/{owned.conversation_id}/begin",
            json={"siteId": "plasmodb"},
        )

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "STRATEGY_NOT_FOUND"


async def test_a_non_owner_is_refused_by_every_route(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    owned: Owned,
    in_memory_jobs: InMemoryConnector,
) -> None:
    del patch_app_db_engine, in_memory_jobs
    intruder = await make_user(db_session)

    offenders: list[str] = []
    ambiguous: list[str] = []
    async with client_for(ends_at_first_frame(app), intruder.id) as client:
        for case in cases(owned):
            status = await status_for(client, case)
            waiver = NO_OWNER_CONTRAST.get((case.method, case.route))
            if status not in REFUSAL_STATUSES:
                offenders.append(f"{case.method} {case.url} -> {status}")
            elif waiver is not None and status != waiver.non_owner_status:
                ambiguous.append(f"{case.method} {case.url} -> {status}")

    assert offenders == [], (
        "routes that served a non-owner instead of 403/404: " + "; ".join(offenders)
    )
    assert ambiguous == [], (
        "routes excused from the owner contrast must refuse with the one status "
        "their waiver names; these answered otherwise: " + "; ".join(ambiguous)
    )


async def test_another_application_is_refused_by_every_route(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    owned: Owned,
    other_application: str,
    in_memory_jobs: InMemoryConnector,
) -> None:
    """A resource is owned by a user under one application, not by the user alone.

    The owner contrast that proves these refusals is
    :func:`test_the_owner_is_not_refused_by_any_route`, which issues the same
    requests as the same user under the application that holds the resources.
    """
    del patch_app_db_engine, db_session, other_application, in_memory_jobs

    offenders: list[str] = []
    client = other_application_client_for(ends_at_first_frame(app), owned.user_id)
    async with client:
        for case in cases(owned):
            status = await status_for(client, case)
            if status not in REFUSAL_STATUSES:
                offenders.append(f"{case.method} {case.url} -> {status}")

    assert offenders == [], (
        "routes that served another application's request for this user's "
        "resources instead of 403/404: " + "; ".join(offenders)
    )


async def test_the_owner_is_not_refused_by_any_route(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    app_memory_store: MemoryStore,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    """The same request, from the owner, must not be refused.

    A refusal here means the non-owner's refusal proves nothing. Every case
    gets its own resources, so a case that deletes cannot disturb the next.
    """
    del patch_app_db_engine, in_memory_jobs, signed_in_to_veupathdb

    offenders: list[str] = []
    contrasted = 0
    for index, blueprint in enumerate(_BLUEPRINTS):
        key = (blueprint.method, blueprint.route)
        if key in NO_OWNER_CONTRAST:
            continue
        fresh = await create_owned(db_session, app_memory_store)
        case = cases(fresh)[index]
        async with client_for(ends_at_first_frame(app), fresh.user_id) as client:
            status = await status_for(client, case)
        contrasted += 1
        if status in OWNER_REFUSAL_STATUSES:
            offenders.append(f"{case.method} {case.url} -> {status}")

    expected = len(_BLUEPRINTS) - len(NO_OWNER_CONTRAST)
    assert contrasted == expected, (
        f"the owner contrast ran {contrasted} of {len(_BLUEPRINTS)} cases"
    )
    assert offenders == [], (
        "routes that answered 404 to their own owner, so the non-owner 404 "
        "proves nothing: " + "; ".join(offenders)
    )
