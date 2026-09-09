from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import DBSessionFactory
from langgraph.runtime import Runtime
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy.session import StrategySession

from pathfinder.ai.agents.compactor import (
    CompactionResult,
    CompactorDeps,
    build_compactor_agent,
)
from pathfinder.ai.graph import nodes
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import (
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.scratchpad.compactor import maybe_compact_scratchpad
from pathfinder.domain.scratchpad.models import NoteCreate
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.scratchpad import ScratchpadRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.research.literature_search import LiteratureSearchService
from pathfinder.services.research.web_search import WebSearchService


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


class TestTriggerGate:
    async def test_noop_under_budget(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
        seed_user: User,
    ) -> None:
        repo = ScratchpadRepository(db_session)
        await repo.create(
            conversation_id=conv_id,
            data=NoteCreate(title="t", summary="s", body="b"),
        )
        await db_session.commit()

        result = await maybe_compact_scratchpad(
            conversation_id=conv_id,
            user_id=seed_user.id,
            db_session_factory=db_session_factory,
        )
        assert result is None

    async def test_skip_when_all_notes_pinned(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
        seed_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """All pinned + no compactable notes → compactor never runs.

        Regression for MAJOR 2: the old gate used ``totals`` (pinned
        included), which triggered compaction even though the only thing
        compaction can touch is the non-pinned tail. Pinned-only scratchpads
        would loop forever burning LLM cost.
        """
        monkeypatch.setattr(
            "pathfinder.ai.scratchpad.compactor.COMPACT_COUNT_THRESHOLD",
            1,
        )

        repo = ScratchpadRepository(db_session)
        for i in range(3):
            await repo.create(
                conversation_id=conv_id,
                data=NoteCreate(
                    title=f"pin{i}",
                    summary="s",
                    body="b",
                    pinned=True,
                ),
            )
        await db_session.commit()

        result = await maybe_compact_scratchpad(
            conversation_id=conv_id,
            user_id=seed_user.id,
            db_session_factory=db_session_factory,
        )
        assert result is None

    async def test_triggers_over_count(
        self,
        db_session: AsyncSession,
        db_session_factory: DBSessionFactory,
        conv_id: UUID,
        seed_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Force small threshold for speed.
        monkeypatch.setattr(
            "pathfinder.ai.scratchpad.compactor.COMPACT_COUNT_THRESHOLD",
            2,
        )

        repo = ScratchpadRepository(db_session)
        for i in range(3):
            await repo.create(
                conversation_id=conv_id,
                data=NoteCreate(title=f"t{i}", summary="s", body="b"),
            )
        await db_session.commit()

        # Force compactor agent to return a 1-note result via TestModel override.
        fixed_output = CompactionResult(
            notes=[NoteCreate(title="merged", summary="s", body="b")],
        )

        def _fake_build_agent(
            *,
            model_id: str | None = None,
        ) -> Agent[CompactorDeps, CompactionResult]:
            agent = build_compactor_agent(model_id=model_id)
            agent.model = TestModel(custom_output_args=fixed_output)
            return agent

        monkeypatch.setattr(
            "pathfinder.ai.scratchpad.compactor.build_compactor_agent",
            _fake_build_agent,
        )

        run = await maybe_compact_scratchpad(
            conversation_id=conv_id,
            user_id=seed_user.id,
            db_session_factory=db_session_factory,
        )
        assert run is not None
        assert run.before_count == 3
        assert run.after_count == 1
        assert run.trigger_reason in ("count", "both")
        assert run.model_id, "the run must record the model that compacted"


@dataclass
class _Runtime:
    context: Context | None


@pytest.mark.usefixtures("patch_app_db_engine")
async def test_finalize_triggers_compactor(
    db_session: AsyncSession,
    db_session_factory: DBSessionFactory,
    conv_id: UUID,
    seed_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del db_session
    calls: list[UUID] = []

    async def _fake_compact(
        *,
        conversation_id: UUID,
        user_id: UUID,
        db_session_factory: DBSessionFactory,
    ) -> None:
        del user_id, db_session_factory
        calls.append(conversation_id)

    def _fake_writer() -> Any:
        def _write(payload: dict[str, Any]) -> None:
            del payload

        return _write

    monkeypatch.setattr(nodes, "maybe_compact_scratchpad", _fake_compact)
    monkeypatch.setattr(nodes, "get_stream_writer", _fake_writer)

    state = PipelineState(
        conversation_id=conv_id,
        user_id=seed_user.id,
        site_id="plasmodb",
        mode="strategy",
        domain=StrategyDomainState(
            verification_digest=VerificationDigest(
                disposition=PhaseDisposition.DONE,
                prose="ok",
                reason="verified",
                success=True,
            ),
        ),
    )
    context = Context(
        site_id="plasmodb",
        user_id=seed_user.id,
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=db_session_factory,
        web_search_service=WebSearchService(),
        literature_search_service=LiteratureSearchService(),
        cancel_event=asyncio.Event(),
    )
    runtime = _Runtime(context=context)

    await nodes.finalize_turn_node(state, cast("Runtime[Context]", runtime))
    assert calls == [conv_id]
