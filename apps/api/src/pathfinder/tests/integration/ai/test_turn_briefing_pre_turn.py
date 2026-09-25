"""The pre-turn hook briefs the Lead on what moved since it last answered.

A parameter set on the strategy the thread answers to, a task the worker
finished and an analysis mutated outside the thread all reach the turn that
follows them. The tasks and the analysis are read from Postgres; the strategy
is the tree the thread answered to against the one the session holds.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import (
    BackgroundTask,
    Conversation,
    ConversationEvent,
    Message,
)
from assistant_core.platform import db
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.pre_turn import pathfinder_pre_turn
from pathfinder.ai.tools.standalone.eda_stream_parts import eda_analysis_state_chunk
from pathfinder.domain.eda_parts import EdaAnalysisState
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.persistence.models import ConversationAnalysis, User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.conversation_update import ConversationUpdate
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.tests._support.recorded_searches import (
    serve_recorded_definitions,
    suite_search,
)

_PERCENTILE = suite_search("search_genes_by_rnaseq_gomez_diaz_percentile")


@pytest.fixture(autouse=True)
def recorded_definitions(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded_definitions(monkeypatch, [_PERCENTILE])


def _ast(percentile: int) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_expr",
            search_name=_PERCENTILE.url_segment,
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


async def _bind_analysis(
    conversation_id: UUID, *, revision: int, shown: int, analysis_id: str = "an_1"
) -> None:
    """Bind ``analysis_id`` and show the card of analysis ``an_1``."""
    async with db.async_session_factory() as session:
        session.add(
            ConversationAnalysis(
                conversation_id=conversation_id,
                site_id="plasmodb",
                dataset_id="DS_1234",
                analysis_id=analysis_id,
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


def _session_holding(percentile: int | None) -> StrategySession:
    """The session the turn runs on, holding the strategy as it stands now."""
    session = StrategySession(site_id="plasmodb")
    if percentile is None:
        return session
    graph = StrategyGraph(graph_id="g1", name="briefing", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(_ast(percentile).root)
    graph.recompute_roots()
    session.graph = graph
    return session


def _context(percentile: int | None = None) -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=_session_holding(percentile),
        db_session_factory=db.async_session_factory,
        cancel_event=asyncio.Event(),
    )


def _state(conversation_id: UUID, answered: int | None = None) -> PipelineState:
    """A thread that answered to the strategy at ``answered``, or to none."""
    return PipelineState(
        conversation_id=conversation_id,
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="what does the strategy do now?",
        domain=StrategyDomainState(
            answered_graph=None if answered is None else _ast(answered),
        ),
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
        tool_name="run_control_tests_on_step",
        completed_at=answered_at + timedelta(seconds=1),
    )
    await _bind_analysis(conversation_id, revision=3, shown=1)

    briefed = await pathfinder_pre_turn(
        _state(conversation_id, answered=90), _context(75)
    )

    rendered = briefed.domain.turn_briefing
    assert "min_expression_percentile 90 -> 75" in rendered
    assert "run_control_tests_on_step finished" in rendered
    assert (
        "- the open analysis (DS_1234) changed after the card in this conversation"
        in rendered
    )
    assert briefed.domain.open_eda_analysis is not None
    assert briefed.domain.open_eda_analysis.changed_after_the_card


async def test_a_rebind_the_thread_never_showed_is_briefed_as_a_change(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A binding restarts its revision, so the card of the old document is behind."""
    del patch_app_db_engine, db_cleaner
    conversation_id, _ = await _seed_thread()
    await _write_strategy(conversation_id, 90)
    await _answer(conversation_id)
    await _bind_analysis(conversation_id, revision=1, shown=3, analysis_id="an_2")

    briefed = await pathfinder_pre_turn(
        _state(conversation_id, answered=90), _context(90)
    )

    assert briefed.domain.turn_briefing.splitlines()[1] == (
        "- the open analysis (DS_1234) changed after the card in this conversation"
    )


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

    briefed = await pathfinder_pre_turn(
        _state(conversation_id, answered=90), _context(90)
    )

    assert briefed.domain.turn_briefing == ""


async def test_a_quiet_thread_is_briefed_with_nothing(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    conversation_id, _ = await _seed_thread()
    await _write_strategy(conversation_id, 90)
    await _answer(conversation_id)

    briefed = await pathfinder_pre_turn(
        _state(conversation_id, answered=90), _context(90)
    )

    assert briefed.domain.turn_briefing == ""
