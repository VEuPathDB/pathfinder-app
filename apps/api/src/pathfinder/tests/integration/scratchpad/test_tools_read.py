from __future__ import annotations

from uuid import UUID

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import DBSessionFactory
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import RunContext
from pydantic_ai.usage import RunUsage
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy.session import StrategySession

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.scratchpad import tools
from pathfinder.domain.scratchpad.models import NoteListResult, NoteSearchResult
from pathfinder.persistence.models import User


@pytest.fixture
async def conv_id(db_session: AsyncSession, seed_user: User) -> UUID:
    conv = Conversation(
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
        tool_name="list_notes",
        tool_call_id="tc-1",
    )


class TestListNotes:
    async def test_list_returns_refs(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session
        ctx = _run_ctx(conv_id=conv_id, db_session_factory=db_session_factory)
        await tools.note(ctx, title="T1", summary="S1", body="B1")
        await tools.note(ctx, title="T2", summary="S2", body="B2", tags=["alpha"])
        result = (await tools.list_notes(ctx)).return_value
        assert isinstance(result, NoteListResult)
        assert result.total_notes == 2
        titles = [ref.title for ref in result.matches]
        assert "T1" in titles
        assert "T2" in titles

    async def test_list_by_tag(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session
        ctx = _run_ctx(conv_id=conv_id, db_session_factory=db_session_factory)
        await tools.note(ctx, title="T1", summary="S", body="B", tags=["alpha"])
        await tools.note(ctx, title="T2", summary="S", body="B", tags=["beta"])
        result = (await tools.list_notes(ctx, tag="alpha")).return_value
        assert isinstance(result, NoteListResult)
        assert [ref.title for ref in result.matches] == ["T1"]

    async def test_list_by_pinned(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session
        ctx = _run_ctx(conv_id=conv_id, db_session_factory=db_session_factory)
        await tools.note(ctx, title="T1", summary="S", body="B")
        await tools.note(ctx, title="T2", summary="S", body="B", pinned=True)
        result = (await tools.list_notes(ctx, pinned=True)).return_value
        assert isinstance(result, NoteListResult)
        assert [ref.title for ref in result.matches] == ["T2"]

    async def test_list_empty_scratchpad_surfaces_summary(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session
        ctx = _run_ctx(conv_id=conv_id, db_session_factory=db_session_factory)
        result = (await tools.list_notes(ctx)).return_value
        assert isinstance(result, NoteListResult)
        assert result.total_notes == 0
        assert result.matches == []
        assert "No notes saved" in result.summary


class TestSearchNotes:
    async def test_search_fts(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session
        ctx = _run_ctx(conv_id=conv_id, db_session_factory=db_session_factory)
        await tools.note(
            ctx,
            title="GenesByRNASeq candidate",
            summary="stage differential",
            body="gametocyte threshold 2",
        )
        await tools.note(
            ctx,
            title="GenesByGO dead end",
            summary="lost specificity",
            body="irrelevant",
        )
        result = (
            await tools.search_notes(ctx, query="gametocyte threshold")
        ).return_value
        assert isinstance(result, NoteSearchResult)
        titles = [ref.title for ref in result.matches]
        assert any("GenesByRNASeq" in title for title in titles)
        assert result.query == "gametocyte threshold"

    async def test_search_empty_scratchpad_surfaces_summary(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session
        ctx = _run_ctx(conv_id=conv_id, db_session_factory=db_session_factory)
        result = (await tools.search_notes(ctx, query="anything")).return_value
        assert isinstance(result, NoteSearchResult)
        assert result.total_notes == 0
        assert result.matches == []
        assert "No notes saved" in result.summary

    async def test_search_no_match_but_notes_exist(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session
        ctx = _run_ctx(conv_id=conv_id, db_session_factory=db_session_factory)
        await tools.note(
            ctx, title="unrelated", summary="s", body="nothing matches here"
        )
        result = (await tools.search_notes(ctx, query="zqzqzq")).return_value
        assert isinstance(result, NoteSearchResult)
        assert result.total_notes == 1
        assert result.matches == []
        assert "No notes match" in result.summary
        assert "1 notes total" in result.summary


class TestReadNote:
    async def test_read_returns_body(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session
        ctx = _run_ctx(conv_id=conv_id, db_session_factory=db_session_factory)
        created = await tools.note(ctx, title="T", summary="S", body="FULL BODY")
        assert isinstance(created.return_value, dict)
        nid = created.return_value["id"]
        assert isinstance(nid, str)
        full = (await tools.read_note(ctx, note_id=nid)).return_value
        assert full["body"] == "FULL BODY"
        assert full["bodyTokens"] == len("FULL BODY") // 4

    async def test_read_missing_raises(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
    ) -> None:
        del db_session
        ctx = _run_ctx(conv_id=conv_id, db_session_factory=db_session_factory)
        with pytest.raises(ModelRetry):
            await tools.read_note(ctx, note_id="n-nope")
