"""A new request over a thread with no steps is framed from its own words alone."""

from __future__ import annotations

from typing import Any

import pytest

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.dispatch_context import (
    agent_deps_for,
    framing_goal,
    the_edit_the_strategy_owes,
)
from pathfinder.ai.lead.edit_messages import edit_work_order
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.intent_gate import tools_the_turn_offers
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.tests.unit.ai.lead._answered_draft import (
    QUESTION,
    classify,
    draft_deps,
    framed,
)
from pathfinder.tests.unit.ai.lead.conftest import requirement, session_with_one_step

_OLD = "surface vaccine candidates in P. falciparum 3D7"
_NEW = "Forget that. Find transporters on chromosome 5."
_ORGANISM = requirement(ConstraintKind.ORGANISM, "organism", "P. falciparum 3D7")


def _old_request(*, built: bool = False) -> StrategyDomainState:
    """A thread that framed the old request, asked about it, and built nothing."""
    return StrategyDomainState(
        operational_spec=framed(None),
        open_questions=[QUESTION],
        requirements=[_ORGANISM],
        recommendations=[_ORGANISM],
        original_request=_OLD,
        last_build_outcome=BuildOutcome(pushed_step_ids=["old"]) if built else None,
    )


def _new_request(domain: StrategyDomainState) -> LeadDeps:
    deps = draft_deps(_NEW, domain=domain)
    classify(deps, IntentClassification.NEW_STRATEGY)
    return deps


def _edit_order(deps: LeadDeps, spec: OperationalSpec) -> str:
    """The edit work order the dispatch writes over ``spec``."""
    answered, pending = the_edit_the_strategy_owes(deps.state, spec)
    return edit_work_order(
        "edit to the new request",
        _NEW,
        spec,
        pending=pending,
        answered=answered,
        answer=deps.state.turn_markers.answered,
    )


def test_a_new_request_over_an_unbuilt_draft_sets_the_request_state_aside() -> None:
    domain = _new_request(_old_request(built=True)).state.domain

    assert domain.operational_spec is None
    assert domain.requirements == []
    assert domain.recommendations == []
    assert domain.open_questions == []
    assert domain.original_request == _NEW
    assert domain.last_build_outcome is None


def test_the_fresh_order_reads_the_new_request_alone() -> None:
    deps = _new_request(_old_request())

    order = frame_work_order("frame the new request", deps)

    assert order.splitlines()[:2] == [
        "FRAME work order: frame the new request",
        f"User's goal: {_NEW}",
    ]
    assert framing_goal(deps.state) == _NEW
    draft = agent_deps_for(deps).agent_state.operational_spec_draft
    assert (draft.goal, draft.criteria) == (_NEW, [])


def test_a_new_request_over_a_built_strategy_keeps_the_request() -> None:
    deps = draft_deps(
        _NEW, domain=_old_request(), strategy_session=session_with_one_step()
    )

    classify(deps, IntentClassification.NEW_STRATEGY)

    domain = deps.state.domain
    assert domain.original_request == _OLD
    assert domain.requirements == [_ORGANISM]
    assert domain.operational_spec == framed(None)


def test_a_new_request_over_a_built_strategy_reaches_the_edit_as_no_answer() -> None:
    deps = draft_deps(
        _NEW, domain=_old_request(), strategy_session=session_with_one_step()
    )
    classify(deps, IntentClassification.NEW_STRATEGY)
    spec = deps.state.domain.operational_spec
    assert spec is not None

    order = _edit_order(deps, spec)

    assert order.splitlines()[:3] == [
        "EDIT work order: edit to the new request",
        f"The user's message: {_NEW}",
        "",
    ]
    assert QUESTION.question not in order


def test_a_reclassification_keeps_the_frame_this_turn_already_ran() -> None:
    """A reclassification after this turn framed sets nothing aside."""
    deps = draft_deps(_NEW, domain=StrategyDomainState(original_request=_NEW))
    classify(deps, IntentClassification.EXTEND_STRATEGY)
    deps.state.domain.operational_spec = framed("signal peptide")
    deps.state.turn_markers.framed = True

    classify(deps, IntentClassification.NEW_STRATEGY, call_id="t_classify_2")

    assert deps.state.domain.operational_spec == framed("signal peptide")
    assert deps.state.domain.original_request == _NEW
    offered = tools_the_turn_offers(deps, ["frame_problem", "build_strategy"])
    assert offered == frozenset({"build_strategy"})


def test_a_reclassification_keeps_the_request_this_turn_already_built() -> None:
    """A reclassification after this turn wrote the strategy sets nothing aside."""
    deps = draft_deps(_NEW, domain=_old_request())
    classify(deps, IntentClassification.EXTEND_STRATEGY)
    deps.state.turn_markers.built = True

    classify(deps, IntentClassification.NEW_STRATEGY, call_id="t_classify_2")

    domain = deps.state.domain
    assert domain.original_request == _OLD
    assert domain.requirements == [_ORGANISM]
    assert domain.operational_spec == framed(None)


def test_a_reclassification_keeps_the_answers_a_consult_took_this_turn() -> None:
    """A consult the researcher answered is work, though it licenses a new frame."""
    deps = draft_deps(_NEW, domain=_old_request())
    classify(deps, IntentClassification.EXTEND_STRATEGY)
    deps.state.turn_markers.consulted = True

    classify(deps, IntentClassification.NEW_STRATEGY, call_id="t_classify_2")

    assert deps.state.domain.requirements == [_ORGANISM]
    assert deps.state.domain.original_request == _OLD


def test_a_reclassification_to_a_new_request_before_any_frame_sets_the_old_aside() -> (
    None
):
    """The classifier corrects itself before any work, so the old request goes."""
    deps = draft_deps(_NEW, domain=_old_request())
    classify(deps, IntentClassification.FOLLOW_UP_QUESTION)

    classify(deps, IntentClassification.NEW_STRATEGY, call_id="t_classify_2")

    domain = deps.state.domain
    assert domain.original_request == _NEW
    assert domain.requirements == []
    assert domain.open_questions == []
    assert agent_deps_for(deps).agent_state.operational_spec_draft.criteria == []
    assert framing_goal(deps.state) == _NEW


def test_a_reclassification_to_a_new_request_over_steps_drops_the_answer() -> None:
    """The questions a new request sets aside are not answered by it."""
    deps = draft_deps(
        _NEW, domain=_old_request(), strategy_session=session_with_one_step()
    )
    classify(deps, IntentClassification.CLARIFICATION_RESPONSE)
    assert deps.state.turn_markers.answered is not None

    classify(deps, IntentClassification.NEW_STRATEGY, call_id="t_classify_2")

    assert deps.state.turn_markers.answered is None
    assert deps.state.domain.original_request == _OLD
    spec = deps.state.domain.operational_spec
    assert spec is not None
    order = _edit_order(deps, spec)
    assert order.splitlines()[:3] == [
        "EDIT work order: edit to the new request",
        f"The user's message: {_NEW}",
        "",
    ]
    assert QUESTION.question not in order


def _stopping_frame(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Each FRAME pass binds one criterion and stops at its budget."""
    orders: list[str] = []

    async def _stopped(**kwargs: Any) -> None:
        orders.append(kwargs["run"].work_order)
        agent_deps: AgentDeps = kwargs["agent_deps"]
        deps: LeadDeps = kwargs["deps"]
        draft = agent_deps.agent_state.operational_spec_draft
        draft.criteria.append(
            Criterion(
                id=f"c_{len(draft.criteria)}", text="a transporter", search_name="S"
            )
        )
        deps.last_phase_stop = PhaseStop(
            role="frame",
            reason=PhaseStopReason.BUDGET,
            tool_calls=60,
            criteria_bound=len(draft.criteria),
            criteria_declared=3,
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _stopped)
    return orders


_BUDGET_RETRY = (
    "FRAME work order: the previous pass ran out of its tool budget. "
    "Continue it; this is not a fresh frame."
)


async def test_the_budget_retry_of_a_new_request_continues_the_fresh_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orders = _stopping_frame(monkeypatch)
    deps = _new_request(_old_request())

    await run_frame(
        deps=deps,
        parent_tool_call_id="f1",
        work_order=frame_work_order("frame the new request", deps),
    )

    assert [order.splitlines()[0] for order in orders] == [
        "FRAME work order: frame the new request",
        _BUDGET_RETRY,
    ]
    assert orders[1].splitlines()[1] == f"User's goal: {_NEW}"
    assert "- [c_0] a transporter -> S" in orders[1]


async def test_the_budget_retry_over_a_draft_with_no_step_is_no_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unbound draft is no strategy, so its retry owes no disposition."""
    orders = _stopping_frame(monkeypatch)
    unbound = OperationalSpec(
        goal=_OLD, criteria=[Criterion(id="c_surface", text="on the surface")]
    )
    deps = draft_deps(_NEW, domain=StrategyDomainState(operational_spec=unbound))
    classify(deps)

    await run_frame(
        deps=deps,
        parent_tool_call_id="f1",
        work_order=frame_work_order("frame the request", deps),
    )

    assert orders[1].splitlines()[0] == _BUDGET_RETRY
