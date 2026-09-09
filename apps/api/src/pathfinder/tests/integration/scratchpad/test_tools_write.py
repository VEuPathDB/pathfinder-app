from __future__ import annotations

from uuid import UUID

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import DBSessionFactory
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import RunContext
from pydantic_ai.usage import RunUsage
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy.session import StrategySession
from veupathdb_mcp.tool_errors import ToolErrorPayload

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.scratchpad import tools
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.scratchpad import ScratchpadRepository
from pathfinder.platform.errors import ErrorCode
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID


@pytest.fixture
async def conv_id(db_session: AsyncSession, seed_user: User) -> UUID:
    conv = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        user_id=seed_user.id,
        site_id="plasmodb",
        name="",
    )
    db_session.add(conv)
    await db_session.flush()
    await db_session.commit()
    return conv.id


def _run_ctx(
    *,
    conv_id: UUID,
    db_session_factory: DBSessionFactory,
) -> RunContext[AgentDeps]:
    deps = AgentDeps(
        site_id="plasmodb",
        strategy_session=StrategySession(site_id="plasmodb"),
        conversation_id=conv_id,
        db_session_factory=db_session_factory,
    )
    return RunContext(
        deps=deps,
        model=TestModel(),
        usage=RunUsage(),
        tool_name="note",
        tool_call_id="tc-1",
    )


class TestNote:
    async def test_note_creates_and_returns_toolreturn(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session
        ctx = _run_ctx(conv_id=conv_id, db_session_factory=db_session_factory)
        result = await tools.note(
            ctx,
            title="Candidate",
            summary="Summary.",
            body="Body.",
            tags=["candidate"],
            pinned=False,
        )
        assert isinstance(result, ToolReturn)
        assert result.metadata
        assert result.metadata[0].type == "data-scratchpad-updated"
        ref = result.return_value
        assert isinstance(ref, dict)
        note_id = ref["id"]
        assert isinstance(note_id, str)
        assert note_id.startswith("n-")
        async with db_session_factory() as session:
            repo = ScratchpadRepository(session)
            fetched = await repo.get(conversation_id=conv_id, note_id=note_id)
            assert fetched is not None
            assert fetched.title == "Candidate"


class TestUpdateAndDeleteAndPin:
    async def test_update_patch_body(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session
        ctx = _run_ctx(conv_id=conv_id, db_session_factory=db_session_factory)
        created = await tools.note(ctx, title="T", summary="S", body="B")
        assert isinstance(created.return_value, dict)
        nid = created.return_value["id"]
        assert isinstance(nid, str)
        updated = await tools.update_note(ctx, note_id=nid, body="B2")
        assert isinstance(updated.return_value, dict)
        assert updated.return_value["title"] == "T"

    async def test_delete(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session
        ctx = _run_ctx(conv_id=conv_id, db_session_factory=db_session_factory)
        created = await tools.note(ctx, title="T", summary="S", body="B")
        assert isinstance(created.return_value, dict)
        nid = created.return_value["id"]
        assert isinstance(nid, str)
        result = await tools.delete_note(ctx, note_id=nid)
        assert result.return_value == "deleted"

    async def test_pin_toggle(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session
        ctx = _run_ctx(conv_id=conv_id, db_session_factory=db_session_factory)
        created = await tools.note(ctx, title="T", summary="S", body="B")
        assert isinstance(created.return_value, dict)
        nid = created.return_value["id"]
        assert isinstance(nid, str)
        pinned = await tools.pin_note(ctx, note_id=nid)
        assert isinstance(pinned.return_value, dict)
        assert pinned.return_value["pinned"] is True
        unpinned = await tools.unpin_note(ctx, note_id=nid)
        assert isinstance(unpinned.return_value, dict)
        assert unpinned.return_value["pinned"] is False


class TestErrorDiscipline:
    async def test_update_missing_raises_modelretry(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session
        ctx = _run_ctx(conv_id=conv_id, db_session_factory=db_session_factory)
        with pytest.raises(ModelRetry):
            await tools.update_note(ctx, note_id="n-missing", title="x")

    async def test_delete_missing_raises_modelretry(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session
        ctx = _run_ctx(conv_id=conv_id, db_session_factory=db_session_factory)
        with pytest.raises(ModelRetry):
            await tools.delete_note(ctx, note_id="n-missing")

    async def test_pin_missing_raises_modelretry(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session
        ctx = _run_ctx(conv_id=conv_id, db_session_factory=db_session_factory)
        with pytest.raises(ModelRetry):
            await tools.pin_note(ctx, note_id="n-missing")

    async def test_missing_context_returns_error_payload(
        self,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session_factory, conv_id
        deps = AgentDeps(
            site_id="plasmodb",
            strategy_session=StrategySession(site_id="plasmodb"),
        )
        ctx = RunContext(
            deps=deps,
            model=TestModel(),
            usage=RunUsage(),
            tool_name="note",
            tool_call_id="tc-1",
        )
        result = await tools.note(ctx, title="t", summary="s", body="b")
        assert isinstance(result.return_value, ToolErrorPayload)
        assert result.return_value.ok is False
        assert result.return_value.code == ErrorCode.NOT_FOUND.value
