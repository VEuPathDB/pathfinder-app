"""A frame or edit pass reads which parts of the message the Lead answers, so
it never records an ask as a requirement or an unstated entry."""

from __future__ import annotations

from pathfinder.ai.lead.dispatch_context import framing_goal, message_asks
from pathfinder.ai.lead.dispatch_messages import (
    answered_question_work_order,
    earlier_turn_work_order,
    stopped_pass_work_order,
)
from pathfinder.ai.lead.edit_messages import EditMessage, edit_work_order
from pathfinder.ai.lead.frame_dispatch import frame_work_order
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.questions import OpenQuestion
from pathfinder.domain.strategy.spec_diff import SpecDiff
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

# A hostdb message that changes a value and asks for a sample of the result.
_MESSAGE = (
    "Put it back to chromosome 17 and show me a sample of five genes from the result."
)
_ASK = "show me a sample of five genes from the result"
_OPERATIONALIZE = (
    "Operationalize into criteria, bind each to a real WDK search, resolve "
    "params, set the structure. Return a FrameResult."
)
_TOLD = (
    "The Lead answers the message's asks after this pass: "
    f"'{_ASK}'. An ask states no requirement, so no criterion and no `unstated` "
    "entry holds one."
)


def _intent(classification: IntentClassification) -> UserIntent:
    return UserIntent(
        classification=classification,
        inferred_goal="Restore chromosome 17 and show five genes.",
        asks=[_ASK],
    )


def test_the_asks_are_the_parts_of_the_message_the_lead_answers() -> None:
    state = pipeline_state("hostdb", user_prompt=_MESSAGE)

    assert [
        message_asks(
            lead_deps(state, intent=_intent(IntentClassification.EDIT_STRATEGY))
        ),
        message_asks(lead_deps(state)),
    ] == [[_ASK], []]


def test_an_edit_pass_is_told_the_asks() -> None:
    spec = OperationalSpec(goal="chromosome 17 genes with an MHC class I GO term")

    order = edit_work_order(
        "restore chromosome 17",
        EditMessage(prompt=_MESSAGE, asks=(_ASK,)),
        spec,
        pending=SpecDiff(),
        answered=spec,
    )

    assert order.splitlines()[2] == _TOLD


def test_a_frame_pass_is_told_the_asks() -> None:
    state = pipeline_state("hostdb", user_prompt=_MESSAGE)
    deps = lead_deps(state, intent=_intent(IntentClassification.NEW_STRATEGY))

    assert frame_work_order("frame the request", deps).splitlines() == [
        "FRAME work order: frame the request",
        f"User's goal: {framing_goal(state)}",
        _TOLD,
        _OPERATIONALIZE,
    ]


def test_every_continuation_of_a_frame_pass_is_told_the_asks() -> None:
    spec = OperationalSpec(goal="chromosome 17 genes with an MHC class I GO term")
    stop = PhaseStop(
        role="frame", reason=PhaseStopReason.BUDGET, tool_calls=12, tool_name=""
    )
    question = OpenQuestion(
        question="Which chromosome?", dimension=ConstraintKind.OTHER
    )
    orders = [
        earlier_turn_work_order(
            spec, spec.goal, message=_MESSAGE, brief="continue", asks=[_ASK]
        ),
        answered_question_work_order(
            spec, spec.goal, [question], answer="17", brief="continue", asks=[_ASK]
        ),
        stopped_pass_work_order(spec, _MESSAGE, stop, asks=[_ASK]),
    ]

    assert [order.splitlines().count(_TOLD) for order in orders] == [1, 1, 1]
