"""What marks a turn as having written to the strategy, and as having checked it."""

from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.conversation.serde import build_checkpoint_serde
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.ai.graph.state import (
    CreatedControlSet,
    StrategyDomainState,
    TurnMarkers,
)
from pathfinder.ai.lead.lead_tools import clear_strategy
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import conversation
from pathfinder.assistants.pathfinder_spec import PATHFINDER_CHECKPOINT_TYPES
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
)


def _clearing_deps() -> LeadDeps:
    """A turn on a thread that holds one step."""
    state = pipeline_state(user_prompt="Scrap it and start over.")
    state.user_message_id = uuid4()
    return lead_deps(state, strategy_session=session_with_one_step())


def _step_ids(deps: LeadDeps) -> list[str]:
    graph = deps.runtime.strategy_session.get_graph(None)
    return [] if graph is None else sorted(graph.steps)


def test_a_turn_that_wrote_nothing_changed_no_strategy() -> None:
    assert TurnMarkers().changed_strategy is False


def test_a_built_turn_changed_the_strategy() -> None:
    assert TurnMarkers(built=True).changed_strategy is True


def test_an_edited_turn_changed_the_strategy() -> None:
    assert TurnMarkers(edited=True).changed_strategy is True


def test_a_turn_that_built_nothing_has_no_unverified_build() -> None:
    assert TurnMarkers().build_unverified is False


def test_a_build_no_pass_checked_is_unverified() -> None:
    assert TurnMarkers(built=True).build_unverified is True


def test_a_verified_build_is_not_unverified() -> None:
    assert TurnMarkers(built=True, verified=True).build_unverified is False


def test_a_dispatched_verification_settles_the_build() -> None:
    """A dispatch that reported failure already checked the build."""
    markers = TurnMarkers(built=True, verification_dispatched=True)

    assert markers.build_unverified is False


@pytest.fixture
def no_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    """The clear runs against the in-memory graph and writes no row."""

    async def _persisted(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        conversation, "persist_strategy_ast_to_conversation", _persisted
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("no_persistence")
async def test_a_cleared_strategy_marks_the_turn() -> None:
    deps = _clearing_deps()

    await clear_strategy(run_context_for(deps), confirm=True)

    assert _step_ids(deps) == []
    assert deps.state.turn_markers.edited is True
    assert deps.state.turn_markers.changed_strategy is True


@pytest.mark.asyncio
@pytest.mark.usefixtures("no_persistence")
async def test_an_unconfirmed_clear_marks_nothing() -> None:
    deps = _clearing_deps()

    with pytest.raises(ModelRetry):
        await clear_strategy(run_context_for(deps), confirm=False)

    assert _step_ids(deps) == ["step_a"]
    assert deps.state.turn_markers.edited is False
    assert deps.state.turn_markers.changed_strategy is False


def test_what_a_turn_saved_survives_the_checkpoint_serializer() -> None:
    """A turn parked on a worker resumes with the record of what it wrote."""
    markers = TurnMarkers(message_id=uuid4())
    markers.record_control_set(CreatedControlSet(id="cs-1", name="rhoptry controls"))
    markers.record_gene_set(
        CreatedGeneSet(id="gs-2", name="rhoptry positives", gene_count=102),
    )
    serde = build_checkpoint_serde(PATHFINDER_CHECKPOINT_TYPES)
    domain = StrategyDomainState(turn_markers=markers)

    resumed = serde.loads_typed(serde.dumps_typed(domain)).turn_markers

    assert [(c.id, c.name) for c in resumed.created_control_sets] == [
        ("cs-1", "rhoptry controls"),
    ]
    assert [(g.id, g.name, g.gene_count) for g in resumed.created_gene_sets] == [
        ("gs-2", "rhoptry positives", 102),
    ]
