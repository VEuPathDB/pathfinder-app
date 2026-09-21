"""The two recorded facts: the spec the strategy answers to, and its tree.

Every path that makes the strategy state what the spec says records both, and
a thread that has never recorded them takes the strategy it already holds.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.pre_turn import refresh_live_strategy_state
from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    SpecStructure,
    structure_criteria,
)
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    PROTEOME,
    canvas_sets,
    with_the_percentile,
    with_the_proteome,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    ROOT,
    STAGE,
    STAGE_TIMEPOINT,
    SURFACE,
    DisagreementThread,
    built_spec,
    built_tree,
    declared,
    joined,
    kept,
    leaf,
    recorded,
    session_holding,
)
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


def _thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    return DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )


def _unbuilt(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    """A thread with a framed plan and no strategy at all."""
    return DisagreementThread(monkeypatch, spec=built_spec(), session=session_holding())


async def test_a_build_makes_the_strategy_answer_to_the_spec_it_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _unbuilt(monkeypatch)
    await thread.next_turn()

    await thread.build()

    domain = thread.deps.state.domain
    assert domain.answered_spec == domain.operational_spec
    assert domain.answered_graph == thread.graph.to_strategy_ast()
    assert structure_criteria(thread.answered.structure) == {
        c.id for c in thread.answered.criteria
    }


async def test_a_pushed_edit_makes_the_strategy_answer_to_the_edited_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert [c.id for c in thread.answered.criteria] == [SURFACE, STAGE, PROTEOME]
    assert thread.deps.state.domain.answered_graph == thread.graph.to_strategy_ast()


async def test_an_edit_with_nothing_to_push_makes_the_plan_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The strategy already states it, so the plan became the answer with no push."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(lambda found: found, declared=kept(SURFACE, STAGE))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert thread.committed == []
    assert thread.deps.state.domain.answered_spec == thread.spec


async def test_a_delete_makes_the_strategy_answer_to_what_is_left(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    await thread.next_turn()

    await thread.delete(STAGE)

    assert [c.id for c in thread.answered.criteria] == [SURFACE]
    assert thread.deps.state.domain.answered_graph == thread.graph.to_strategy_ast()


async def test_a_clear_leaves_the_thread_answering_to_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    await thread.next_turn()

    await thread.clear()

    domain = thread.deps.state.domain
    assert (domain.answered_spec, domain.answered_graph) == (None, None)
    assert thread.graph.steps == {}


async def test_a_value_the_user_set_is_not_pushed_back_by_the_next_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The answer holds the canvas value, so the next diff reads no movement."""
    thread = _thread(monkeypatch)
    canvas_sets(thread.graph, STAGE, timepoint=NumberValue(value=48))
    await thread.next_turn()
    thread.frames(
        with_the_percentile(90),
        declared=[*kept(SURFACE), *declared("changed", STAGE)],
    )

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert [op.kind for op in thread.committed] == ["updateStepParams"]
    assert thread.graph.steps[STAGE].parameters[STAGE_TIMEPOINT] == NumberValue(
        value=48
    )


def _hydrating_thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    """A thread whose checkpoint holds no spec at all."""
    thread = _thread(monkeypatch)
    thread.deps.state.domain.operational_spec = None
    thread.deps.state.domain.answered_spec = None
    thread.deps.state.domain.answered_graph = None
    return thread


async def test_a_hydrated_thread_answers_to_the_spec_derived_from_its_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _hydrating_thread(monkeypatch)

    await thread.next_turn()

    domain = thread.deps.state.domain
    assert [c.id for c in thread.answered.criteria] == [SURFACE, STAGE]
    assert domain.answered_spec == domain.operational_spec
    assert domain.answered_graph == thread.graph.to_strategy_ast()


def _domain_of(
    spec: OperationalSpec | None, *, before_dispatch: OperationalSpec | None = None
) -> StrategyDomainState:
    return StrategyDomainState(
        operational_spec=spec,
        spec_before_dispatch=before_dispatch,
        last_build_outcome=recorded(SURFACE, STAGE, ROOT),
    )


async def _refreshed(
    monkeypatch: pytest.MonkeyPatch, domain: StrategyDomainState
) -> StrategyDomainState:
    """One turn of an existing thread that has recorded no answer yet."""
    thread = _thread(monkeypatch)
    state = pipeline_state(user_prompt="carry on", domain=domain)
    deps = lead_deps(state, strategy_session=thread.session)
    refreshed = await refresh_live_strategy_state(state, deps.runtime)
    return refreshed.domain


async def test_an_existing_thread_answers_to_the_plan_it_already_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing is pending, so the plan and the answer are one spec."""
    domain = await _refreshed(monkeypatch, _domain_of(built_spec()))

    plan = domain.operational_spec
    assert plan is not None
    assert domain.answered_spec == plan
    assert [c.id for c in plan.criteria] == [SURFACE, STAGE]


async def test_an_existing_thread_with_a_draft_pending_answers_to_the_pre_draft_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The draft asked a question; the strategy answers to what the dispatch found."""
    pending = built_spec()
    pending.criteria.append(with_the_proteome(2)(built_spec()).criteria[-1])
    assert pending.structure is not None
    pending.structure = SpecStructure(
        root=joined(CombineOp.INTERSECT, pending.structure.root, leaf(PROTEOME))
    )

    domain = await _refreshed(
        monkeypatch, _domain_of(pending, before_dispatch=built_spec())
    )

    answered = domain.answered_spec
    plan = domain.operational_spec
    assert answered is not None
    assert plan is not None
    assert [c.id for c in answered.criteria] == [SURFACE, STAGE]
    assert [c.id for c in plan.criteria] == [SURFACE, STAGE, PROTEOME]


async def test_a_thread_with_no_spec_and_no_strategy_answers_to_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _unbuilt(monkeypatch)

    await thread.next_turn()

    domain = thread.deps.state.domain
    assert (domain.answered_spec, domain.answered_graph) == (None, None)
    assert [c.id for c in thread.spec.criteria] == [SURFACE, STAGE]


async def test_a_turn_stopped_after_an_edit_leaves_the_answer_the_edit_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The checkpoint holds both facts, so the next turn replays nothing."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))
    await thread.edit()
    stopped = thread.deps.state.domain.model_copy(deep=True)

    await thread.next_turn()

    domain = thread.deps.state.domain
    assert domain.answered_spec == stopped.answered_spec
    assert domain.answered_graph == stopped.answered_graph
    assert domain.operational_spec == stopped.operational_spec
