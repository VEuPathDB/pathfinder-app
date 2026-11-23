from __future__ import annotations

import json
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import ConversationEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.types import ASGIApp

from strategist.persistence.models import User
from strategist.tests.integration.http._share_support import (
    anonymous,
    checkpoint_tables,
    seed_owners_state,
    seed_thread,
    share_path,
)
from strategist.tests.integration.http.conftest import client_for

pytestmark = pytest.mark.usefixtures(checkpoint_tables.__name__)

UPLOAD = "EDAUD_sF88g1cwo00gw"
NAME = "My 3D7 RNA-seq upload"

UPLOAD_READ = (
    {"type": "start", "messageId": "m-3"},
    {"type": "tool-input-start", "toolCallId": "c-9", "toolName": "open_eda_analysis"},
    {
        "type": "tool-input-available",
        "toolCallId": "c-9",
        "toolName": "open_eda_analysis",
        "input": {"datasetId": UPLOAD, "purpose": "gametocyte subset"},
    },
    {
        "type": "tool-output-available",
        "toolCallId": "c-9",
        "output": {"datasetId": UPLOAD, "studyDisplayName": NAME},
    },
    {
        "type": "data-eda.analysis-state",
        "id": "a-up-1",
        "data": {
            "siteId": "plasmodb",
            "datasetId": UPLOAD,
            "studyId": "STUDY_up_3d7",
            "analysisId": "a-up-1",
            "revision": 1,
            "studyDisplayName": NAME,
            "displayName": "gametocyte subset",
            "numFilters": 0,
            "numComputations": 0,
            "filters": [],
            "filterSummaries": [],
            "entityCounts": [],
            "canExportRows": True,
        },
    },
    {"type": "finish"},
    {"type": "done"},
)


async def _seed_upload_read(
    session_maker: async_sessionmaker[AsyncSession], thread: UUID
) -> None:
    async with session_maker() as session:
        session.add_all(
            ConversationEvent(conversation_id=thread, chunk=chunk)
            for chunk in UPLOAD_READ
        )
        await session.commit()


@pytest.mark.parametrize(
    ("include_account_reads", "shown"), [(False, False), (True, True)]
)
async def test_the_snapshot_names_the_owners_upload_only_with_the_account_reads(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    include_account_reads: bool,
    shown: bool,
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    await _seed_upload_read(session_maker, thread)
    made = (
        await authed_client.put(
            share_path(thread),
            json={
                "public": True,
                "allowCopy": False,
                "includeAccountReads": include_account_reads,
            },
        )
    ).json()

    async with anonymous(app) as viewer:
        got = await viewer.get(f"/api/v1/shared/{made['share']['token']}/snapshot")

    assert got.status_code == 200
    assert [UPLOAD in got.text, NAME in got.text] == [shown, shown]


async def test_a_copy_without_the_account_reads_names_no_upload(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    signed_in_to_veupathdb: None,
) -> None:
    del signed_in_to_veupathdb
    thread = await seed_thread(session_maker, authed_user_id)
    await seed_owners_state(session_maker, thread)
    await _seed_upload_read(session_maker, thread)
    made = (
        await authed_client.put(
            share_path(thread), json={"public": True, "allowCopy": True}
        )
    ).json()
    viewer_id = uuid4()
    async with session_maker() as session:
        session.add(User(id=viewer_id))
        await session.commit()

    async with client_for(app, viewer_id) as viewer:
        copied = await viewer.post(f"/api/v1/shared/{made['share']['token']}/copy")

    async with session_maker() as session:
        chunks = (
            await session.scalars(
                select(ConversationEvent.chunk).where(
                    ConversationEvent.conversation_id == UUID(copied.json()["id"])
                )
            )
        ).all()
    copy = json.dumps(list(chunks))
    assert copied.status_code == 200
    assert [UPLOAD in copy, NAME in copy, "Kinases on chromosome 3." in copy] == [
        False,
        False,
        True,
    ]
