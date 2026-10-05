"""A Lead run adds one exchange to the conversation: the researcher's message
or card answer, the reply it showed, and the card it ended on."""

from __future__ import annotations

from assistant_core.graph.turn_state import ParkedCall, PendingApproval
from pydantic_ai.ui.vercel_ai.request_types import ToolApprovalResponded

from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_exchange import turn_exchange
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.domain.exchanges import Exchange
from pathfinder.tests._support.run_context import lead_run_context

_ASKED = "Keep SRP171130 then. Exclude anything also expressed in male antennae."


def _card(call_id: str) -> PendingApproval:
    return PendingApproval(
        phase="lead",
        tool_call_id=call_id,
        tool_name="consult_user",
        tool_args={
            "reply": "The study has three male antennae samples.",
            "questions": [
                {
                    "id": "q0",
                    "prompt": "Which male antennae samples should I exclude?",
                    "options": [{"label": "All three"}, {"label": "None"}],
                }
            ],
        },
    )


def test_a_typed_reply_is_the_exchange_of_the_message() -> None:
    ctx = lead_run_context(user_prompt=_ASKED)
    capture = _LeadRunCapture(
        response=LeadResponse(
            prose="The strategy keeps 12 genes.", strategy_changed=False
        )
    )

    assert turn_exchange(ctx.deps.state, capture) == Exchange(
        said=_ASKED, reply="The strategy keeps 12 genes."
    )


def test_a_card_turn_keeps_the_card_it_asked() -> None:
    ctx = lead_run_context(user_prompt=_ASKED)
    capture = _LeadRunCapture(pending_approval=_card("call_card"))

    assert turn_exchange(ctx.deps.state, capture) == Exchange(
        said=_ASKED,
        reply="The study has three male antennae samples.",
        card="Which male antennae samples should I exclude? (options: All three; None)",
    )


def test_an_answered_approval_is_the_researchers_words() -> None:
    ctx = lead_run_context(user_prompt=_ASKED)
    ctx.deps.state.approval_responses["call_card"] = ToolApprovalResponded(
        id="call_card", approved=False, reason="use the female set only"
    )
    capture = _LeadRunCapture(
        answered_call=_card("call_card"),
        response=LeadResponse(prose="I kept the female set.", strategy_changed=False),
    )

    assert turn_exchange(ctx.deps.state, capture) == Exchange(
        kind="card_answer",
        said="no: use the female set only",
        reply="I kept the female set.",
    )


def test_a_worker_result_is_a_task_exchange() -> None:
    ctx = lead_run_context(user_prompt=_ASKED)
    capture = _LeadRunCapture(
        answered_call=ParkedCall(
            phase="lead",
            tool_call_id="call_task",
            tool_name="run_control_tests_on_step",
        ),
        response=LeadResponse(
            prose="4 of 5 positive controls are in the result.", strategy_changed=False
        ),
    )

    assert turn_exchange(ctx.deps.state, capture) == Exchange(
        kind="task_result", reply="4 of 5 positive controls are in the result."
    )
