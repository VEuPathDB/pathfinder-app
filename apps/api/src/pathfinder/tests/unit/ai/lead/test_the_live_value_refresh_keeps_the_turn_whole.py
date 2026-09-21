"""Who owns a value, the plan or the strategy, measured at the turn seam.

The spec and the graph are one address space and two value forms: the criterion
states the term a user or the model named, the step holds the form VEuPathDB
took. The two tests marked ``xfail`` pin the cases that are still wrong.

The refresh, the dispatch checks, the diff and the planner are the production
ones; only the FRAME pass, the sheet read and the commit are stand-ins.
"""

from __future__ import annotations

import pytest
from pydantic_ai.tools import DeferredToolResults
from veupathdb.domain.parameters import MultiPickValue, NumberValue

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.dispatch_context import record_the_spec_the_dispatch_found
from pathfinder.ai.lead.sub_agent_stream import SubAgentResume
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    PROTEOME,
    with_the_percentile,
    with_the_proteome,
)
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

_ORGANISM = "organism"
_BRANCH = MultiPickValue(values=["Anopheles"])
_LEAVES = MultiPickValue(values=["Anopheles gambiae PEST", "Anopheles stephensi"])


def _thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    return DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )


def _bound_to_a_branch_term(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    """The criterion states the branch; the pushed step holds its leaves."""
    spec = built_spec()
    for criterion in spec.criteria:
        if criterion.id == STAGE:
            criterion.resolved_params = {
                **criterion.resolved_params,
                _ORGANISM: _BRANCH,
            }
    thread = DisagreementThread(
        monkeypatch,
        spec=spec,
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )
    thread.graph.steps[STAGE].parameters[_ORGANISM] = _LEAVES
    return thread


def _stage_value(spec: OperationalSpec, name: str) -> object:
    return next(c for c in spec.criteria if c.id == STAGE).resolved_params[name]


async def test_a_branch_term_the_criterion_states_is_not_replaced_by_its_leaves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The step holds the submitted form of the same choice, not another choice."""
    thread = _bound_to_a_branch_term(monkeypatch)

    await thread.next_turn()

    assert _stage_value(thread.spec, _ORGANISM) == _BRANCH


async def test_restating_the_branch_term_on_a_kept_criterion_is_no_movement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _bound_to_a_branch_term(monkeypatch)
    await thread.next_turn()

    def _draft(found: OperationalSpec) -> OperationalSpec:
        for criterion in found.criteria:
            if criterion.id == STAGE:
                criterion.resolved_params = {
                    **criterion.resolved_params,
                    _ORGANISM: _BRANCH,
                }
        return with_the_proteome(2)(found)

    thread.frames(_draft, declared=kept(SURFACE, STAGE))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert [op.kind for op in thread.committed] == ["addLeaf", "addCombine"]


async def test_a_value_set_while_a_call_was_parked_costs_the_resumed_pass_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The record the resumed pass is measured against states the same live value."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    record_the_spec_the_dispatch_found(thread.deps, resume=None)
    thread.graph.steps[STAGE].parameters[STAGE_TIMEPOINT] = NumberValue(value=48)
    await thread.next_turn(resumes_parked_call=True)
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))

    delta = await thread.edit(
        resume=SubAgentResume(messages=[], results=DeferredToolResults())
    )

    assert isinstance(delta, EditDelta)
    assert thread.graph.steps[STAGE].parameters[STAGE_TIMEPOINT] == NumberValue(
        value=48
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "An edit that ends needs_user commits its draft as the thread's spec, "
        "so a changed value on a built criterion becomes the next dispatch's "
        "baseline, the next diff calls it kept, and it is never pushed while "
        "the spec claims it. A changed value on a built criterion in an edit "
        "that ends needs_user must be pushed by the follow-up that answers the "
        "question."
    ),
)
async def test_a_change_framed_beside_an_open_question_is_pushed_once_it_is_answered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first turn states a new value and asks; the second answers and builds."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(
        lambda found: with_the_proteome(None)(with_the_percentile(90)(found)),
        declared=[],
        disposition="needs_user",
    )
    await thread.edit()
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE, PROTEOME))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert thread.graph.steps[STAGE].parameters[STAGE_PERCENTILE] == NumberValue(
        value=90
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "A value the user sets on the canvas does not reach the thread's spec: "
        "the spec states what the last frame bound while the strategy holds "
        "what the user set, so the workspace, the ledger and the reply describe "
        "a strategy the user no longer has. Nothing writes the stale value to "
        "the step. A canvas edit must move the value it wrote into the spec."
    ),
)
async def test_a_value_set_on_the_canvas_reaches_the_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    thread.graph.steps[STAGE].parameters[STAGE_TIMEPOINT] = NumberValue(value=48)

    await thread.next_turn()

    assert _stage_value(thread.spec, STAGE_TIMEPOINT) == NumberValue(value=48)
