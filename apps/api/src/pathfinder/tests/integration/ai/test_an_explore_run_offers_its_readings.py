from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic_ai import DeferredToolRequests
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.ai.explore.explore_agent import build_explore_agent
from pathfinder.ai.explore.readings_card import card_labels, counted_labels
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.models.mock import get_mock_model
from pathfinder.ai.models.mock.explore_arc import FIRST_LABEL, SECOND_LABEL
from pathfinder.ai.models.mock.strategy_specs import GENE_TYPE, SIGNAL_PEPTIDE
from pathfinder.tests._support.explore_turns import (
    EXPLORE_PROMPT,
    GENE_TYPE_REPORT,
    NO_READING_PROMPT,
    SITE,
    RecordedReports,
    seed_count,
    serve_recorded_readings,
)
from pathfinder.tests._support.recorded_counts import recorded_count
from pathfinder.tests._support.run_context import turn_runtime


@pytest.fixture
def reports(monkeypatch: pytest.MonkeyPatch) -> RecordedReports:
    return serve_recorded_readings(monkeypatch)


def explore_deps(
    prompt: str, session_maker: async_sessionmaker[AsyncSession]
) -> LeadDeps:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id=SITE,
        mode="explore",
        user_prompt=prompt,
        user_message_id=uuid4(),
    )
    bind_scripted_scope(SITE, prompt)
    return LeadDeps(
        state=state,
        intent=None,
        runtime=turn_runtime(
            site_id=SITE, user_id=state.user_id, db_session_factory=session_maker
        ),
        retrieved_memories=[],
    )


async def test_the_explore_arc_counts_two_readings_and_offers_them(
    session_maker: async_sessionmaker[AsyncSession], reports: RecordedReports
) -> None:
    deps = explore_deps(EXPLORE_PROMPT, session_maker)

    result = await build_explore_agent().run(
        deps.state.user_prompt, deps=deps, model=get_mock_model()
    )

    assert isinstance(result.output, DeferredToolRequests)
    [call] = result.output.approvals
    assert call.tool_name == "consult_user"
    assert card_labels(call.args_as_dict()) == [FIRST_LABEL, SECOND_LABEL]
    assert counted_labels(deps) == {
        FIRST_LABEL: seed_count(),
        SECOND_LABEL: recorded_count(GENE_TYPE_REPORT),
    }
    assert [name for name, _ in reports.ran] == [SIGNAL_PEPTIDE, GENE_TYPE]
    assert deps.state.domain.named_readings == []
    assert deps.state.domain.requirements == []
    assert deps.state.domain.operational_spec is None
    assert deps.runtime.strategy_session.get_graph(None) is None


async def test_a_reply_with_no_buildable_reading_ends_with_no_card(
    session_maker: async_sessionmaker[AsyncSession], reports: RecordedReports
) -> None:
    deps = explore_deps(NO_READING_PROMPT, session_maker)

    result = await build_explore_agent().run(
        deps.state.user_prompt, deps=deps, model=get_mock_model()
    )

    assert isinstance(result.output, str)
    assert result.output.startswith("[mock]")
    assert reports.ran == []
    assert counted_labels(deps) == {}
