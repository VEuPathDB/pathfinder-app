from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.types import ASGIApp

from strategist.tests._support.shared_strategy import (
    PRIVATE_DATASET_ID,
    STATE,
    UPLOAD_AST,
    UPLOADED_STUDY,
    WDK_STRATEGY_ID,
)
from strategist.tests.integration.http._share_support import (
    anonymous,
    checkpoint_tables,
    seed_strategy,
    seed_study,
    seed_thread,
    share_path,
)

pytestmark = pytest.mark.usefixtures(checkpoint_tables.__name__)


async def test_a_new_link_carries_the_context_by_default(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)

    made = (
        await authed_client.put(
            share_path(thread), json={"public": True, "allowCopy": False}
        )
    ).json()
    async with anonymous(app) as viewer:
        head = (await viewer.get(f"/api/v1/shared/{made['share']['token']}")).json()

    assert made["share"]["includeContext"] is True
    assert head["includeContext"] is True


async def test_the_owner_can_leave_the_context_out(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)

    made = (
        await authed_client.put(
            share_path(thread),
            json={"public": True, "allowCopy": False, "includeContext": False},
        )
    ).json()
    async with anonymous(app) as viewer:
        head = (await viewer.get(f"/api/v1/shared/{made['share']['token']}")).json()

    assert made["share"]["includeContext"] is False
    assert (await authed_client.get(share_path(thread))).json()["share"][
        "includeContext"
    ] is False
    assert head["includeContext"] is False


def _leaves(value: object) -> Iterator[object]:
    match value:
        case dict():
            for item in value.values():
                yield from _leaves(item)
        case list():
            for item in value:
                yield from _leaves(item)
        case _:
            yield value


async def _shared(
    authed_client: httpx.AsyncClient, thread: UUID, **settings: bool
) -> str:
    made = await authed_client.put(
        share_path(thread), json={"public": True, "allowCopy": False, **settings}
    )
    return str(made.json()["share"]["token"])


async def test_the_viewer_reads_the_strategy_without_the_private_list(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    await seed_strategy(session_maker, thread)
    token = await _shared(authed_client, thread)

    async with anonymous(app) as viewer:
        got = await viewer.get(f"/api/v1/shared/{token}/context")

    body = got.json()
    steps = body["strategy"]["steps"]
    assert got.status_code == 200
    assert PRIVATE_DATASET_ID not in got.text
    assert {WDK_STRATEGY_ID, 900117, 900118, 900119}.isdisjoint(_leaves(body))
    assert body["privateInputs"] == {"s-list": ["ds_gene_ids"]}
    assert (body["strategy"]["wdkUrl"], body["strategy"]["wdkStrategyId"]) == (
        None,
        None,
    )
    assert body["strategy"]["id"] != str(thread)
    assert {s["id"]: s["estimatedSize"] for s in steps} == {
        "s-list": 41,
        "s-text": 1204,
        "s-both": 12,
    }
    assert [s["wdkStepId"] for s in steps] == [None, None, None]
    assert body["study"] is None


async def test_the_account_reads_box_carries_the_list(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    await seed_strategy(session_maker, thread)
    token = await _shared(authed_client, thread, includeAccountReads=True)

    async with anonymous(app) as viewer:
        got = await viewer.get(f"/api/v1/shared/{token}/context")

    assert PRIVATE_DATASET_ID in got.text
    assert got.json()["privateInputs"] == {}


async def test_a_link_without_the_context_refuses_it(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    await seed_strategy(session_maker, thread)
    token = await _shared(authed_client, thread, includeContext=False)

    async with anonymous(app) as viewer:
        got = await viewer.get(f"/api/v1/shared/{token}/context")

    assert (got.status_code, got.json()["code"]) == (403, "SHARE_CONTEXT_NOT_SHARED")
    assert "kinase" not in got.text


async def test_the_context_needs_the_links_password(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    await seed_strategy(session_maker, thread)
    made = (
        await authed_client.put(
            share_path(thread), json={"public": False, "allowCopy": False}
        )
    ).json()
    token = made["share"]["token"]

    async with anonymous(app) as viewer:
        locked = await viewer.get(f"/api/v1/shared/{token}/context")
        opened = await viewer.get(
            f"/api/v1/shared/{token}/context",
            headers={"X-Share-Password": made["password"]},
        )

    assert (locked.status_code, locked.json()["code"]) == (403, "SHARE_LOCKED")
    assert opened.status_code == 200


async def test_the_study_is_the_bound_analysis_as_the_thread_showed_it(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    await seed_study(session_maker, thread, dataset_id=STATE.dataset_id)
    token = await _shared(authed_client, thread)

    async with anonymous(app) as viewer:
        got = await viewer.get(f"/api/v1/shared/{token}/context")

    study = got.json()["study"]
    assert (study["analysisId"], study["studyDisplayName"]) == (
        "a-1",
        STATE.study_display_name,
    )
    assert (study["analysisUrl"], study["canExportRows"]) == (None, False)
    assert "/eda/a-1" not in got.text


@pytest.mark.parametrize(
    ("include_account_reads", "shown"), [(False, False), (True, True)]
)
async def test_a_study_on_the_owners_upload_needs_the_account_reads(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    include_account_reads: bool,
    shown: bool,
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    await seed_study(session_maker, thread, dataset_id=UPLOADED_STUDY)
    token = await _shared(
        authed_client, thread, includeAccountReads=include_account_reads
    )

    async with anonymous(app) as viewer:
        got = await viewer.get(f"/api/v1/shared/{token}/context")

    assert (got.json()["study"] is not None) is shown
    assert (STATE.study_display_name in got.text) is shown


async def test_the_head_names_the_strategy_revision(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    await seed_strategy(session_maker, thread)
    token = await _shared(authed_client, thread)

    owner = (await authed_client.get(f"/api/v1/conversations/{thread}")).json()
    async with anonymous(app) as viewer:
        head = (await viewer.get(f"/api/v1/shared/{token}")).json()
        await _shared(authed_client, thread, includeContext=False)
        closed = (await viewer.get(f"/api/v1/shared/{token}")).json()

    assert head["strategyRevision"] == owner["strategyRevision"] != ""
    assert closed["strategyRevision"] == ""


async def test_no_step_field_carries_the_private_list(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    await seed_strategy(session_maker, thread)
    token = await _shared(authed_client, thread)

    owner = await authed_client.get(f"/api/v1/conversations/{thread}")
    async with anonymous(app) as viewer:
        got = await viewer.get(f"/api/v1/shared/{token}/context")

    step = next(s for s in got.json()["strategy"]["steps"] if s["id"] == "s-list")
    assert PRIVATE_DATASET_ID in owner.text
    assert PRIVATE_DATASET_ID not in got.text
    assert (step["rationale"], step["validation"]["errors"]) == (None, None)
    assert step["wdkPushError"] == "This step failed on the site."
    assert [f["value"] for f in step["filters"]] == [None]
    assert [a["parameters"] for a in step["analyses"]] == [{}]


@pytest.mark.parametrize(
    ("include_account_reads", "shown"), [(False, False), (True, True)]
)
async def test_an_analysis_on_the_owners_upload_names_it_nowhere(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    include_account_reads: bool,
    shown: bool,
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    await seed_strategy(session_maker, thread, UPLOAD_AST)
    token = await _shared(
        authed_client, thread, includeAccountReads=include_account_reads
    )

    owner = await authed_client.get(f"/api/v1/conversations/{thread}")
    async with anonymous(app) as viewer:
        got = await viewer.get(f"/api/v1/shared/{token}/context")

    (step,) = got.json()["strategy"]["steps"]
    assert owner.json()["steps"][0]["rationale"]["datasetId"] == UPLOADED_STUDY
    assert (UPLOADED_STUDY in got.text) is shown
    assert "EDAUD_" not in got.text or shown
    assert (step["estimatedSize"], step["displayName"]) == (
        230,
        "Genes up in my upload",
    )
    assert (step["rationale"] is not None) is shown
