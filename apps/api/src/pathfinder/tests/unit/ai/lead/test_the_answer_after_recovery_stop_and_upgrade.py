"""The answered facts after a recovery pass, a stopped turn and an upgrade."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import NumberValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.answered_strategy import (
    live_tree,
    the_thread_wrote_the_strategy,
)
from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.pre_turn import refresh_live_strategy_state
from pathfinder.domain.strategy.operational_spec import OpenSlot, OperationalSpec
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    PROTEOME,
    canvas_sets,
    with_the_percentile,
    with_the_proteome,
)
from pathfinder.tests.unit.ai.lead._disagreement_facts import OpFacts, committed_facts
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    ROOT,
    STAGE,
    STAGE_PERCENTILE,
    STAGE_TIMEPOINT,
    SURFACE,
    DisagreementThread,
    built_spec,
    built_tree,
    kept,
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


def _value(spec: OperationalSpec | None, name: str) -> NumberValue:
    assert spec is not None
    value = next(c for c in spec.criteria if c.id == STAGE).resolved_params[name]
    assert isinstance(value, NumberValue)
    return value


async def test_a_value_recovery_wrote_is_the_answer_and_the_next_edit_leaves_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    await thread.next_turn()
    before = live_tree(thread.graph)
    canvas_sets(thread.graph, STAGE, **{STAGE_TIMEPOINT: NumberValue(value=36)})

    await the_thread_wrote_the_strategy(
        thread.deps.state, site_id="plasmodb", graph=thread.graph, before=before
    )

    domain = thread.deps.state.domain
    assert _value(domain.answered_spec, STAGE_TIMEPOINT) == NumberValue(value=36)
    assert _value(domain.operational_spec, STAGE_TIMEPOINT) == NumberValue(value=36)
    assert _value(domain.spec_before_turn, STAGE_TIMEPOINT) == NumberValue(value=40)
    thread.assert_invariants()
    await thread.next_turn()
    thread.frames(with_the_percentile(90), declared=kept(SURFACE))
    delta = await thread.edit()
    assert isinstance(delta, EditDelta), delta
    assert committed_facts(thread.committed) == [
        OpFacts(
            kind="updateStepParams",
            step_id=STAGE,
            parameters={STAGE_PERCENTILE: "90"},
        )
    ]


async def test_a_stop_that_rolls_the_strategy_back_takes_the_built_criterion_with_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The checkpoint kept the edit's answer and the strategy went back."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))
    await thread.edit()
    assert PROTEOME in thread.graph.steps
    rolled_back = session_holding(built_tree()).get_graph(None)
    assert rolled_back is not None
    thread.graph.steps = rolled_back.steps
    thread.graph.recompute_roots()

    await thread.next_turn()

    assert [c.id for c in thread.answered.criteria] == [SURFACE, STAGE]
    assert thread.criteria == [SURFACE, STAGE]


def _asking_about_a_built_criterion() -> OperationalSpec:
    """A draft that moved the percentile and left the timepoint open."""
    draft = with_the_percentile(90)(built_spec())
    for criterion in draft.criteria:
        if criterion.id == STAGE:
            criterion.resolved_params.pop(STAGE_TIMEPOINT)
            criterion.open_params = [
                OpenSlot(criterion_id=STAGE, param_name=STAGE_TIMEPOINT)
            ]
    return draft


async def test_an_upgraded_thread_whose_draft_moved_a_built_value_still_pushes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The draft is not ready to build, so the answer is what its dispatch found."""
    thread = _thread(monkeypatch)
    state = pipeline_state(
        user_prompt="48 hours",
        domain=StrategyDomainState(
            operational_spec=_asking_about_a_built_criterion(),
            spec_before_dispatch=built_spec(),
            last_build_outcome=recorded(SURFACE, STAGE, ROOT),
        ),
    )
    deps = lead_deps(state, strategy_session=thread.session)

    refreshed = await refresh_live_strategy_state(state, deps.runtime)

    assert _value(refreshed.domain.answered_spec, STAGE_PERCENTILE) == NumberValue(
        value=80
    )


async def test_a_turn_resumed_after_its_own_edit_still_reports_the_step_it_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The entry record is this turn's baseline, so it never gains this turn's step."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))
    await thread.edit()
    assert thread.ledger_diff().added_count == 1

    await thread.next_turn(resumes_parked_call=True)

    assert [c.id for c in thread.before_turn.criteria] == [SURFACE, STAGE]
    assert thread.ledger_diff().added_count == 1
