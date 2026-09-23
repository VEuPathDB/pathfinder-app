"""A FRAME pass that follows an answered question continues the draft it finds.

The bound criteria are listed as done, so the pass spends its calls on the
criterion the answer concerns and leaves the others as they are.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.dispatch_messages import (
    ContinuationReason,
    frame_continuation_work_order,
)
from pathfinder.ai.lead.frame_dispatch import frame_work_order
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import ConstraintKind, OpenQuestion
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._disagreement_facts import spec_facts
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    DisagreementThread,
    declared,
    joined,
    kept,
    leaf,
    session_holding,
)
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_BOUND = ["c_signal", "c_stage", "c_conserved", "c_secreted"]
_OPEN = "c_localised"
_OPEN_PARAM = "evidence"
_QUESTION = OpenQuestion(
    question="No GPI-anchor search is realizable; use signal-peptide evidence?",
    dimension=ConstraintKind.DATA_TYPE,
    recommended_value="signal peptide",
)
_ANSWER = "Go with your recommendation"


def _bound(criterion_id: str) -> Criterion:
    return Criterion(
        id=criterion_id,
        text=f"{criterion_id} property",
        search_name=f"GenesBy_{criterion_id}",
        resolved_params={"value": StringValue(value=criterion_id)},
    )


def _localised(evidence: str | None) -> Criterion:
    return Criterion(
        id=_OPEN,
        text="localised to the surface",
        search_name="GenesBySignalPeptide",
        resolved_params={}
        if evidence is None
        else {_OPEN_PARAM: StringValue(value=evidence)},
        open_params=[]
        if evidence is not None
        else [OpenSlot(criterion_id=_OPEN, param_name=_OPEN_PARAM)],
    )


def _framed(evidence: str | None) -> OperationalSpec:
    """Four bound criteria and the localisation criterion, intersected."""
    root = leaf(_BOUND[0])
    for criterion_id in [*_BOUND[1:], _OPEN]:
        root = joined(CombineOp.INTERSECT, root, leaf(criterion_id))
    return OperationalSpec(
        goal="surface vaccine candidates",
        criteria=[*(_bound(cid) for cid in _BOUND), _localised(evidence)],
        structure=SpecStructure(root=root),
    )


def _answering_state() -> PipelineState:
    """The turn after FRAME asked: the question is answered by this message."""
    state = pipeline_state(
        user_prompt=_ANSWER,
        domain=StrategyDomainState(
            operational_spec=_framed(None), open_questions=[_QUESTION]
        ),
    )
    state.user_message_id = uuid4()
    _classify(state)
    return state


def _classify(state: PipelineState) -> None:
    classify_user_intent(
        run_context_for(lead_deps(state), "t_classify"),
        UserIntent(
            classification=IntentClassification.CLARIFICATION_RESPONSE,
            inferred_goal="use signal-peptide evidence",
        ),
    )


def test_classifying_the_answer_keeps_the_questions_it_answers() -> None:
    state = _answering_state()

    assert state.domain.open_questions == []
    assert state.turn_markers.answered_questions == [_QUESTION]


def test_the_order_after_an_answer_lists_the_bound_criteria_and_the_answer() -> None:
    order = frame_work_order("proceed with signal-peptide evidence", _answering_state())

    assert order.startswith(
        "FRAME work order: the previous pass ended with a question the "
        "researcher has now answered. Continue it; this is not a fresh frame."
    )
    assert (
        "4 criteria are bound already. Do NOT call search_for_searches or "
        "set_criterion for any of them unless the answer below names it:"
    ) in order
    for criterion_id in _BOUND:
        assert f"- [{criterion_id}] {criterion_id} property -> " in order
    assert (
        "These criteria hold open parameters the answer may decide:\n"
        f"- [{_OPEN}] localised to the surface -> GenesBySignalPeptide "
        f"(open: {_OPEN_PARAM})"
    ) in order
    assert f"Question asked: {_QUESTION.question}" in order
    assert f"Answer: {_ANSWER}" in order
    assert "Operationalize into criteria" not in order


def test_a_fresh_thread_gets_the_fresh_order() -> None:
    state = pipeline_state(user_prompt="find surface proteins")

    order = frame_work_order("operationalize the goal", state)

    assert order.startswith("FRAME work order: operationalize the goal")
    assert "Operationalize into criteria" in order


def test_a_built_strategy_is_not_briefed_as_a_continuation() -> None:
    state = _answering_state()
    state.domain.last_build_outcome = BuildOutcome()

    order = frame_work_order("re-frame", state)

    assert "Operationalize into criteria" in order


def test_a_bound_draft_with_no_question_is_continued_from_the_message() -> None:
    state = pipeline_state(
        user_prompt="continue",
        domain=StrategyDomainState(operational_spec=_framed(None)),
    )
    _classify(state)

    order = frame_work_order("continue the frame", state)

    assert order.startswith(
        "FRAME work order: an earlier turn bound the criteria below and no "
        "strategy is built from them yet."
    )
    assert "The user's message: continue" in order
    assert "Question asked" not in order


def test_the_order_after_a_budget_stop_keeps_its_words() -> None:
    order = frame_continuation_work_order(
        _framed(None), "find surface proteins", ContinuationReason.BUDGET_STOP
    )

    assert order.startswith(
        "FRAME work order: the previous pass ran out of its tool budget. "
        "Continue it; this is not a fresh frame."
    )
    assert (
        "5 criteria are bound already and stay exactly as they are. "
        "Do NOT call set_criterion for any of them:"
    ) in order
    assert "Question asked" not in order


async def test_the_answering_turn_binds_only_the_open_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FRAME asks, the researcher answers, the next pass resolves one criterion."""
    thread = DisagreementThread(
        monkeypatch,
        spec=OperationalSpec(goal="surface vaccine candidates"),
        session=session_holding(),
    )
    thread.frames(
        lambda _found: _framed(None),
        declared=[],
        disposition="needs_user",
        asks=[_QUESTION],
    )
    asked = await thread.frame()
    assert isinstance(asked, FrameResult)
    assert asked.disposition == "needs_user"
    await thread.next_turn()
    thread.deps.state.user_prompt = _ANSWER
    thread.deps.state.user_message_id = uuid4()
    _classify(thread.deps.state)
    thread.frames(
        lambda _found: _framed("signal peptide"),
        declared=[*kept(*_BOUND), *declared("changed", _OPEN)],
    )

    answered = await thread.frame()

    assert isinstance(answered, FrameResult)
    order = thread.work_orders[-1]
    assert "the previous pass ended with a question" in order
    assert f"Question asked: {_QUESTION.question}" in order
    assert f"Answer: {_ANSWER}" in order
    assert all(f"- [{cid}] " in order for cid in _BOUND)
    assert [c.id for c in thread.workspaces[-1].criteria if c.bound] == [
        *_BOUND,
        _OPEN,
    ]
    assert spec_facts(thread.spec) == {
        **{cid: {"value": cid} for cid in _BOUND},
        _OPEN: {_OPEN_PARAM: "signal peptide"},
    }
