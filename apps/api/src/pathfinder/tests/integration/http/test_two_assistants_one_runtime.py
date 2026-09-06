"""Two assistants answer through one runtime, each under its own architecture.

PathFinder needs a registered VEuPathDB login and runs its lead graph; site
help needs no WDK identity at all and runs a single agent. Both are dispatched,
worked and streamed by the same pipeline.
"""

from __future__ import annotations

from uuid import uuid4

from assistant_core.persistence.models import Conversation, Message
from fastapi import FastAPI
from langgraph.checkpoint.memory import InMemorySaver
from procrastinate.testing import InMemoryConnector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.assistants.site_help.mock import (
    PROCEED_PREFIX,
    PROCEED_PROMPT,
    SITES_REPLY,
)
from pathfinder.tests.integration.chat._helpers import chat_post_body
from pathfinder.tests.integration.http._two_assistants import (
    SITE_HELP,
    SITES_PROMPT,
    UNAUTHORIZED,
    assistant_of,
    text_of,
    turn,
)
from pathfinder.tests.integration.http.conftest import client_for, make_user
from pathfinder.tests.integration.http.test_wdk_login_required import (
    LOGIN_CODE,
    LOGIN_DETAIL,
    LOGIN_TITLE,
)


async def test_a_site_help_turn_runs_without_any_wdk_login(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    in_memory_jobs: InMemoryConnector,
) -> None:
    """No WDK token, no identity override: the assistant declares no gate."""
    del patch_app_db_engine
    owner = await make_user(db_session)
    conversation_id = uuid4()

    chunks = await turn(
        app,
        owner.id,
        in_memory_jobs,
        conversation_id=conversation_id,
        prompt=SITES_PROMPT,
        assistant_id=SITE_HELP,
    )

    types = [c["type"] for c in chunks]
    assert types[-2:] == ["finish", "done"]
    assert await assistant_of(session_maker, conversation_id) == SITE_HELP


async def test_the_same_request_against_pathfinder_still_needs_a_login(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
) -> None:
    """PathFinder's refusal is unchanged, on the same route, with the same body."""
    del patch_app_db_engine, in_memory_jobs
    owner = await make_user(db_session)
    body = chat_post_body(uuid4(), SITES_PROMPT)

    async with client_for(app, owner.id) as client:
        response = await client.post("/api/v1/chat", json=body, timeout=30.0)

    assert response.status_code == UNAUTHORIZED, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    problem = response.json()
    assert problem["code"] == LOGIN_CODE
    assert problem["title"] == LOGIN_TITLE
    assert problem["detail"] == LOGIN_DETAIL


async def test_the_site_help_turn_answers_from_the_real_sites_service(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
) -> None:
    """The scripted arc calls the catalog tool, which returns the live registry."""
    del patch_app_db_engine
    owner = await make_user(db_session)

    chunks = await turn(
        app,
        owner.id,
        in_memory_jobs,
        conversation_id=uuid4(),
        prompt=SITES_PROMPT,
        assistant_id=SITE_HELP,
    )

    called = [c for c in chunks if c["type"] == "tool-input-available"]
    assert [c["toolName"] for c in called] == ["list_veupathdb_sites"]
    outputs = [c for c in chunks if c["type"] == "tool-output-available"]
    site_ids = {site["site_id"] for site in outputs[0]["output"]}
    assert {"plasmodb", "toxodb", "vectorbase"} <= site_ids
    assert text_of(chunks) == SITES_REPLY


async def test_a_second_site_help_turn_answers_from_the_first(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
) -> None:
    """A bare "yes" names the request the thread made a turn earlier."""
    del patch_app_db_engine
    owner = await make_user(db_session)
    conversation_id = uuid4()
    await turn(
        app,
        owner.id,
        in_memory_jobs,
        conversation_id=conversation_id,
        prompt=SITES_PROMPT,
        assistant_id=SITE_HELP,
    )

    chunks = await turn(
        app,
        owner.id,
        in_memory_jobs,
        conversation_id=conversation_id,
        prompt=PROCEED_PROMPT,
    )

    assert text_of(chunks) == f"{PROCEED_PREFIX}{SITES_PROMPT}"


async def test_the_turn_leaves_an_assistant_message_with_its_usage(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    in_memory_jobs: InMemoryConnector,
) -> None:
    """The runtime's finalize step runs for an assistant that declares no epilogue."""
    del patch_app_db_engine
    owner = await make_user(db_session)
    conversation_id = uuid4()

    await turn(
        app,
        owner.id,
        in_memory_jobs,
        conversation_id=conversation_id,
        prompt=SITES_PROMPT,
        assistant_id=SITE_HELP,
    )

    async with session_maker() as session:
        rows = list(
            await session.scalars(
                select(Message).where(Message.conversation_id == conversation_id),
            ),
        )
    assistant_rows = [row for row in rows if row.role == "assistant"]
    assert len(assistant_rows) == 1
    usage = assistant_rows[0].metadata_["usage"]
    assert usage["totalTokens"] > 0


def test_the_two_assistants_resolve_different_graphs() -> None:
    """One registry, two architectures: the runtime cannot tell them apart."""
    registry = get_assistant_registry()

    pathfinder_nodes = set(
        registry.resolve("pathfinder").build_graph(InMemorySaver()).get_graph().nodes,
    )
    site_help_nodes = set(
        registry.resolve(SITE_HELP).build_graph(InMemorySaver()).get_graph().nodes,
    )

    assert "lead" in pathfinder_nodes
    assert "lead" not in site_help_nodes
    assert "agent" in site_help_nodes
    assert "agent" not in pathfinder_nodes


async def test_a_signed_out_caller_can_begin_a_site_help_conversation(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """The creation path takes the same assistant id the chat body does."""
    del patch_app_db_engine
    owner = await make_user(db_session)
    conversation_id = uuid4()

    async with client_for(app, owner.id) as client:
        response = await client.post(
            f"/api/v1/conversations/{conversation_id}/begin",
            json={"siteId": "plasmodb", "assistantId": SITE_HELP},
        )

    assert response.status_code == 200, response.text
    assert response.json()["isNew"] is True
    assert await assistant_of(session_maker, conversation_id) == SITE_HELP


async def test_begin_refuses_an_assistant_the_thread_was_not_created_under(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    del patch_app_db_engine
    owner = await make_user(db_session)
    conversation = Conversation(
        user_id=owner.id,
        assistant_id="pathfinder",
        site_id="plasmodb",
        name="kinases",
    )
    db_session.add(conversation)
    await db_session.flush()
    await db_session.commit()

    async with client_for(app, owner.id) as client:
        response = await client.post(
            f"/api/v1/conversations/{conversation.id}/begin",
            json={"siteId": "plasmodb", "assistantId": SITE_HELP},
        )

    assert response.status_code == 409, response.text
    assert await assistant_of(session_maker, conversation.id) == "pathfinder"


async def test_begin_without_an_assistant_still_takes_the_default(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    del patch_app_db_engine
    owner = await make_user(db_session)
    conversation_id = uuid4()

    async with client_for(app, owner.id) as client:
        response = await client.post(
            f"/api/v1/conversations/{conversation_id}/begin",
            json={"siteId": "plasmodb"},
        )

    assert response.status_code == 200, response.text
    assert await assistant_of(session_maker, conversation_id) == "pathfinder"
