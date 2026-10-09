from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.conversation.ui_message_reducer import user_message_chunk
from assistant_core.memory.store import MemoryStore
from assistant_core.persistence.models import Conversation, ConversationEvent
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.types import JSONObject
from pydantic_ai.ui.vercel_ai.response_types import TextDeltaChunk
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.graph.stream_events import ledger_update_event
from pathfinder.ai.lead.ledger_sections import VerificationSection
from pathfinder.domain.data_statement import DataStatementVersion
from pathfinder.persistence.repositories.eval_staging import EvalStagingRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.eval_data.extraction import extract_eval_candidates
from pathfinder.tests._support.ledger import ledger_with

PRIVACY = "/api/v1/me/privacy"
NOTICE = "/api/v1/me/privacy/data-notice"
CURRENT = DataStatementVersion.CURRENT.value


def _ledger_chunk() -> JSONObject:
    section = VerificationSection(
        digest=VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="prose",
            reason="ok",
            success=True,
        ),
    )
    return ledger_update_event(ledger=ledger_with(section)).model_dump(
        by_alias=True,
        mode="json",
        exclude_none=True,
    )


def _chunks() -> list[JSONObject]:
    return [
        user_message_chunk(
            message_id=str(uuid4()),
            parts=[{"type": "text", "text": "find x"}],
        ),
        TextDeltaChunk(id="lead-prose-1", delta="Built it.").model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        ),
        _ledger_chunk(),
    ]


async def _stage_one_for(
    session_maker: async_sessionmaker[AsyncSession],
    user_id: UUID,
) -> None:
    async with session_maker() as session:
        conversation_id = uuid4()
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
            ),
        )
        await session.flush()
        for chunk in _chunks():
            session.add(
                ConversationEvent(conversation_id=conversation_id, chunk=chunk),
            )
        await session.commit()
    await extract_eval_candidates()


async def test_a_new_user_reads_consent_on_and_the_notice_due(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.get(PRIVACY)

    assert response.status_code == 200
    assert response.json() == {
        "evalDataConsent": True,
        "dataNoticeSeen": None,
        "noticeDue": True,
    }


async def test_continuing_records_the_version_and_the_choice_in_one_call(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.post(
        NOTICE, json={"version": CURRENT, "evalDataConsent": False}
    )

    assert response.status_code == 200
    assert (await authed_client.get(PRIVACY)).json() == {
        "evalDataConsent": False,
        "dataNoticeSeen": CURRENT,
        "noticeDue": False,
    }


async def test_a_notice_of_another_version_is_refused(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.post(
        NOTICE, json={"version": "2026-01-01", "evalDataConsent": True}
    )

    assert response.status_code == 422
    assert (await authed_client.get(PRIVACY)).json()["dataNoticeSeen"] is None


async def test_opting_out_persists(authed_client: httpx.AsyncClient) -> None:
    response = await authed_client.patch(PRIVACY, json={"evalDataConsent": False})

    assert response.json()["evalDataConsent"] is False
    assert (await authed_client.get(PRIVACY)).json()["evalDataConsent"] is False


async def test_opting_back_in_persists(authed_client: httpx.AsyncClient) -> None:
    await authed_client.patch(PRIVACY, json={"evalDataConsent": False})

    await authed_client.patch(PRIVACY, json={"evalDataConsent": True})

    assert (await authed_client.get(PRIVACY)).json()["evalDataConsent"] is True


async def test_a_change_of_consent_leaves_the_seen_version_alone(
    authed_client: httpx.AsyncClient,
) -> None:
    await authed_client.post(NOTICE, json={"version": CURRENT, "evalDataConsent": True})

    await authed_client.patch(PRIVACY, json={"evalDataConsent": False})

    assert (await authed_client.get(PRIVACY)).json()["dataNoticeSeen"] == CURRENT


async def test_a_user_who_has_not_seen_the_notice_has_nothing_staged(
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    del authed_client
    await _stage_one_for(session_maker, authed_user_id)

    staging = EvalStagingRepository(session_factory=async_session_factory)
    assert await staging.list_staged() == []


async def test_opting_out_through_the_route_clears_staged_candidates(
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await authed_client.post(NOTICE, json={"version": CURRENT, "evalDataConsent": True})
    await _stage_one_for(session_maker, authed_user_id)
    staging = EvalStagingRepository(session_factory=async_session_factory)
    assert len(await staging.list_staged()) == 1

    await authed_client.patch(PRIVACY, json={"evalDataConsent": False})

    assert await staging.list_staged() == []


async def test_continuing_with_the_box_unticked_clears_staged_candidates(
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await authed_client.post(NOTICE, json={"version": CURRENT, "evalDataConsent": True})
    await _stage_one_for(session_maker, authed_user_id)
    staging = EvalStagingRepository(session_factory=async_session_factory)
    assert len(await staging.list_staged()) == 1

    await authed_client.post(
        NOTICE, json={"version": CURRENT, "evalDataConsent": False}
    )

    assert await staging.list_staged() == []


async def test_the_purge_clears_staged_candidates(
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    app_memory_store: MemoryStore,
) -> None:
    del app_memory_store
    await authed_client.post(NOTICE, json={"version": CURRENT, "evalDataConsent": True})
    await _stage_one_for(session_maker, authed_user_id)
    staging = EvalStagingRepository(session_factory=async_session_factory)
    assert len(await staging.list_staged()) == 1

    response = await authed_client.delete("/api/v1/user/data")

    assert response.status_code == 200
    assert response.json()["deleted"]["stagedEvalCases"] == 1
    assert await staging.list_staged() == []


@pytest.mark.parametrize(
    ("method", "path"), [("get", PRIVACY), ("patch", PRIVACY), ("post", NOTICE)]
)
async def test_the_route_needs_a_signed_in_user(
    client: httpx.AsyncClient,
    method: str,
    path: str,
) -> None:
    response = await client.request(method.upper(), path, json={})

    assert response.status_code in {401, 403}
