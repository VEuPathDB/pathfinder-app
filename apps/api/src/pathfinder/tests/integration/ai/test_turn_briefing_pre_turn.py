"""The pre-turn hook briefs the Lead from what Postgres holds.

A parameter edited between two writes, a task the worker finished and an
analysis mutated outside the thread all reach the turn that follows them.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from assistant_core.persistence.models import (
    BackgroundTask,
    Conversation,
    ConversationEvent,
    Message,
)
from assistant_core.platform import db
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.pre_turn import pathfinder_pre_turn
from pathfinder.ai.tools.standalone.eda_stream_parts import eda_analysis_state_chunk
from pathfinder.domain.eda_parts import EdaAnalysisState
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.persistence.models import ConversationAnalysis, User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.conversation_update import ConversationUpdate
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID


def _ast(percentile: int) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_expr",
            search_name="GenesByRNASeqEvidence",
            parameters={"min_expression_percentile": NumberValue(value=percentile)},
            display_name="top expression",
        ),
    )


async def _seed_thread() -> tuple[UUID, UUID]:
    conversation_id, user_id = uuid4(), uuid4()
    async with db.async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name="briefing",
            ),
        )
        await session.commit()
    return conversation_id, user_id


async def _write_strategy(conversation_id: UUID, percentile: int) -> None:
    async with db.async_session_factory() as session:
        await ConversationRepository(session).update_conversation(
            conversation_id,
            ConversationUpdate(
                strategy_ast=_ast(percentile),
                record_type="transcript",
                step_count=1,
                wdk_strategy_id=330534153,
                wdk_strategy_id_set=True,
            ),
        )
        await session.commit()


async def _answer(conversation_id: UUID) -> datetime:
    answered_at = datetime.now(UTC)
    async with db.async_session_factory() as session:
        session.add(
            Message(
                id=uuid4(),
                conversation_id=conversation_id,
                role="assistant",
                created_at=answered_at,
            ),
        )
        await session.commit()
    return answered_at


async def _finish_task(
    conversation_id: UUID,
    user_id: UUID,
    *,
    tool_name: str,
    completed_at: datetime,
) -> None:
    async with db.async_session_factory() as session:
        session.add(
            BackgroundTask(
                id=uuid4(),
                conversation_id=conversation_id,
                user_id=user_id,
                tool_name=tool_name,
                tool_call_id=f"call_{tool_name}",
                args={},
                status="complete",
                estimated_duration_seconds=60,
                completed_at=completed_at,
            ),
        )
        await session.commit()


def _shown_state(revision: int) -> EdaAnalysisState:
    return EdaAnalysisState(
        site_id="plasmodb",
        dataset_id="DS_1234",
        study_id="STUDY_1",
        analysis_id="an_1",
        revision=revision,
        study_display_name="Rodent malaria phenotypes",
        display_name="berghei subset",
        num_filters=0,
        num_computations=0,
        filters=[],
        filter_summaries=[],
        entity_counts=[],
        can_export_rows=False,
    )


async def _bind_analysis(conversation_id: UUID, *, revision: int, shown: int) -> None:
    async with db.async_session_factory() as session:
        session.add(
            ConversationAnalysis(
                conversation_id=conversation_id,
                site_id="plasmodb",
                dataset_id="DS_1234",
                analysis_id="an_1",
                revision=revision,
            ),
        )
        session.add(
            ConversationEvent(
                conversation_id=conversation_id,
                chunk=eda_analysis_state_chunk(_shown_state(shown)).model_dump(
                    by_alias=True,
                    mode="json",
                ),
            ),
        )
        await session.commit()


def _context() -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=db.async_session_factory,
        cancel_event=asyncio.Event(),
    )


def _state(conversation_id: UUID) -> PipelineState:
    return PipelineState(
        conversation_id=conversation_id,
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="what does the strategy do now?",
        domain=StrategyDomainState(),
    )


async def test_the_hook_briefs_the_turn_on_an_edit_a_task_and_the_analysis(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    conversation_id, user_id = await _seed_thread()
    await _write_strategy(conversation_id, 90)
    answered_at = await _answer(conversation_id)
    await _write_strategy(conversation_id, 75)
    await _finish_task(
        conversation_id,
        user_id,
        tool_name="run_gene_set_enrichment",
        completed_at=answered_at + timedelta(seconds=1),
    )
    await _bind_analysis(conversation_id, revision=3, shown=1)

    briefed = await pathfinder_pre_turn(_state(conversation_id), _context())

    rendered = briefed.domain.turn_briefing
    assert "min_expression_percentile 90 -> 75" in rendered
    assert "run_gene_set_enrichment finished" in rendered
    assert "the open analysis (DS_1234) is 2 revisions ahead" in rendered


async def test_a_task_that_finished_before_the_last_answer_is_not_briefed(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    conversation_id, user_id = await _seed_thread()
    await _write_strategy(conversation_id, 90)
    answered_at = await _answer(conversation_id)
    await _finish_task(
        conversation_id,
        user_id,
        tool_name="run_control_tests_on_step",
        completed_at=answered_at - timedelta(seconds=1),
    )

    briefed = await pathfinder_pre_turn(_state(conversation_id), _context())

    assert briefed.domain.turn_briefing == ""


async def test_a_quiet_thread_is_briefed_with_nothing(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    conversation_id, _ = await _seed_thread()
    await _write_strategy(conversation_id, 90)
    await _answer(conversation_id)

    briefed = await pathfinder_pre_turn(_state(conversation_id), _context())

    assert briefed.domain.turn_briefing == ""
