from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from assistant_core.graph.turn_state import (
    DurableCall,
    DurableDeferral,
    DurableTaskResult,
    PendingApproval,
    PendingDurableCall,
)
from assistant_core.platform.types import PaidBy
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.ui.vercel_ai.request_types import ToolApprovalResponded

from strategist.ai.capabilities.metering import ModelSpend, SpendMeter
from strategist.ai.graph._explore_turn import (
    explore_exchange,
    explore_park,
    explore_state_delta,
    explore_turn_for,
    hand_over_reading,
)
from strategist.ai.graph.state import PipelineState, StrategyDomainState
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.models.mock.explore_arc import FIRST_LABEL, SECOND_LABEL
from strategist.ai.tools.standalone.eda_statistics import EDA_PCA
from strategist.domain.exchanges import Exchange
from strategist.domain.modes import EXPLORE_PHASE, READINGS_PHASE
from strategist.tests._support.durable_answers import PCA_RESULT
from strategist.tests._support.run_context import turn_runtime

EXPLORE_PROMPT = "Which genes carry a signal peptide?"
TASK = uuid4()
MESSAGES: list[ModelMessage] = [
    ModelRequest(parts=[UserPromptPart(content=EXPLORE_PROMPT)])
]
PREFERENCE_ARGS: dict[str, Any] = {
    "kind": "preference",
    "name": "stated preference",
    "summary": "I prefer SignalP 6.0.",
    "content": {"statement": "I prefer SignalP 6.0."},
}


def state(**fields: Any) -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="explore",
        user_message_id=fields.pop("user_message_id", uuid4()),
        **fields,
    )


def deps_of(held: PipelineState) -> LeadDeps:
    return LeadDeps(
        state=held,
        intent=None,
        runtime=turn_runtime(user_id=held.user_id),
        retrieved_memories=[],
    )


def _prior() -> str:
    return ModelMessagesTypeAdapter.dump_json(MESSAGES).decode()


def card_of(*labels: str) -> dict[str, Any]:
    return {
        "reply": "Two readings.",
        "questions": [
            {
                "id": "reading",
                "prompt": "Which reading should the strategy build?",
                "options": [{"label": label} for label in labels],
                "allowNotes": False,
            }
        ],
    }


def parked_approval(*, phase: str, tool_name: str, **args: Any) -> PendingApproval:
    return PendingApproval(
        phase=phase,
        tool_call_id="call-card",
        tool_name=tool_name,
        tool_args=args,
        prior_messages_json=_prior(),
    )


def readings_park(*labels: str) -> PendingApproval:
    return parked_approval(
        phase=READINGS_PHASE, tool_name="consult_user", **card_of(*labels)
    )


def pending_durable(*, task_id: UUID) -> PendingDurableCall:
    return PendingDurableCall(
        phase=EXPLORE_PHASE,
        tool_call_id="call-pca",
        tool_name=EDA_PCA.tool_name,
        prior_messages_json=_prior(),
        durable_calls=[
            DurableCall(
                tool_call_id="call-pca",
                tool_name=EDA_PCA.tool_name,
                task_id=task_id,
                durable_tool_name=EDA_PCA.tool_name,
            )
        ],
    )


def responded(approved: bool, reason: str | None = None) -> ToolApprovalResponded:
    return ToolApprovalResponded(id="approval-1", approved=approved, reason=reason)


def deferred(
    *, approvals: Sequence[ToolCallPart] = (), calls: Sequence[ToolCallPart] = ()
) -> DeferredToolRequests:
    return DeferredToolRequests(approvals=list(approvals), calls=list(calls))


def consult_call(*labels: str) -> ToolCallPart:
    return ToolCallPart("consult_user", card_of(*labels), tool_call_id="call-card")


def remember_call() -> ToolCallPart:
    return ToolCallPart("remember", PREFERENCE_ARGS, tool_call_id="call-remember")


def durable_call() -> ToolCallPart:
    return ToolCallPart(EDA_PCA.tool_name, {}, tool_call_id="call-pca")


def test_a_fresh_message_runs_on_its_prompt_and_no_history() -> None:
    turn = explore_turn_for(state(user_prompt="Which stages express these genes?"))

    assert turn.prompt == "Which stages express these genes?"
    assert (turn.history, turn.results, turn.answered, turn.hints) == (
        None,
        None,
        None,
        (),
    )


def test_a_fresh_message_names_its_message_on_the_stream() -> None:
    message_id = uuid4()

    turn = explore_turn_for(
        state(user_prompt=EXPLORE_PROMPT, user_message_id=message_id)
    )

    assert turn.prompt_message_id == str(message_id)


def test_an_answered_preference_card_resumes_the_parked_run() -> None:
    parked = parked_approval(
        phase=EXPLORE_PHASE, tool_name="remember", **PREFERENCE_ARGS
    )

    turn = explore_turn_for(
        state(
            pending_approval=parked,
            approval_responses={parked.tool_call_id: responded(True)},
        )
    )

    assert turn.prompt is None
    assert turn.answered == parked
    assert turn.results is not None
    assert turn.results.approvals == {parked.tool_call_id: True}
    assert [hint.tool_call_id for hint in turn.hints] == [parked.tool_call_id]
    assert turn.history == MESSAGES
    assert turn.prompt_message_id is None


def test_a_typed_message_over_a_card_starts_fresh() -> None:
    parked = parked_approval(
        phase=EXPLORE_PHASE, tool_name="remember", **PREFERENCE_ARGS
    )

    turn = explore_turn_for(
        state(pending_approval=parked, user_prompt="What about orthologs?")
    )

    assert turn.prompt == "What about orthologs?"
    assert (turn.answered, turn.history, turn.results) == (None, None, None)


def test_a_finished_task_resumes_the_parked_run() -> None:
    parked = pending_durable(task_id=TASK)

    turn = explore_turn_for(
        state(
            pending_durable_call=parked,
            durable_result=DurableTaskResult(
                task_id=TASK, status="success", result=PCA_RESULT
            ),
        )
    )

    assert turn.answered == parked
    assert turn.results is not None
    assert list(turn.results.calls) == ["call-pca"]
    assert [hint.tool_call_id for hint in turn.hints] == ["call-pca"]
    assert turn.prompt is None


def test_a_task_still_running_leaves_a_fresh_turn() -> None:
    parked = pending_durable(task_id=TASK)

    turn = explore_turn_for(
        state(pending_durable_call=parked, user_prompt=EXPLORE_PROMPT)
    )

    assert (turn.prompt, turn.answered) == (EXPLORE_PROMPT, None)


def test_a_readings_card_parks_under_the_readings_phase() -> None:
    deps = deps_of(state(user_prompt=EXPLORE_PROMPT))

    park = explore_park(
        deferred(approvals=[consult_call(FIRST_LABEL, SECOND_LABEL)]), deps, MESSAGES
    )

    assert park is not None
    assert (park.phase, park.tool_name) == (READINGS_PHASE, "consult_user")
    assert isinstance(park, PendingApproval)
    assert park.user_message_id == deps.state.user_message_id


def test_a_preference_card_parks_for_explore() -> None:
    deps = deps_of(state(user_prompt=EXPLORE_PROMPT))

    park = explore_park(deferred(approvals=[remember_call()]), deps, MESSAGES)

    assert park is not None
    assert (park.phase, park.tool_name) == (EXPLORE_PHASE, "remember")
    assert isinstance(park, PendingApproval)
    assert park.user_message_id == deps.state.user_message_id


def test_a_durable_call_parks_for_explore() -> None:
    deps = deps_of(state(user_prompt=EXPLORE_PROMPT))
    deps.durable_deferrals["call-pca"] = DurableDeferral(
        task_id=TASK, tool_name=EDA_PCA.tool_name
    )

    park = explore_park(
        deferred(calls=[durable_call()], approvals=[remember_call()]), deps, MESSAGES
    )

    assert isinstance(park, PendingDurableCall)
    assert park.phase == EXPLORE_PHASE
    assert [call.task_id for call in park.durable_calls] == [TASK]


def test_a_run_that_defers_nothing_parks_nothing() -> None:
    deps = deps_of(state(user_prompt=EXPLORE_PROMPT))

    assert [explore_park(deferred(), deps, MESSAGES)] == [None]


def test_the_hand_over_names_the_cards_readings() -> None:
    domain = StrategyDomainState()

    hand_over_reading(domain, readings_park(FIRST_LABEL, SECOND_LABEL))

    assert domain.reading_labels() == [FIRST_LABEL, SECOND_LABEL]
    assert domain.picked_readings == []


def test_the_exchange_of_a_fresh_turn_keeps_the_message() -> None:
    ex = explore_exchange(
        state(user_prompt=EXPLORE_PROMPT),
        reply="Nothing to build.",
        parked=None,
        answered=None,
        counts={},
    )

    assert ex == Exchange(said=EXPLORE_PROMPT, reply="Nothing to build.")


def test_the_exchange_of_a_readings_card_lists_the_counts() -> None:
    ex = explore_exchange(
        state(user_prompt=EXPLORE_PROMPT),
        reply="Two readings.",
        parked=readings_park(FIRST_LABEL, SECOND_LABEL),
        answered=None,
        counts={FIRST_LABEL: 812, SECOND_LABEL: 95},
    )

    assert ex.card == (
        f"Readings offered: {FIRST_LABEL} (812 genes); {SECOND_LABEL} (95 genes)"
    )
    assert (ex.kind, ex.said, ex.reply) == ("message", EXPLORE_PROMPT, "Two readings.")


def test_the_exchange_of_another_park_asks_for_approval() -> None:
    parked = parked_approval(
        phase=EXPLORE_PHASE, tool_name="remember", **PREFERENCE_ARGS
    )

    ex = explore_exchange(
        state(user_prompt=EXPLORE_PROMPT),
        reply="",
        parked=parked,
        answered=None,
        counts={},
    )

    assert ex.card == "approve remember"


def test_the_exchange_of_an_answered_card_says_the_answer() -> None:
    parked = parked_approval(
        phase=EXPLORE_PHASE, tool_name="remember", **PREFERENCE_ARGS
    )
    answered_state = state(
        pending_approval=parked,
        approval_responses={parked.tool_call_id: responded(False, "not now")},
    )

    ex = explore_exchange(
        answered_state, reply="Kept nothing.", parked=None, answered=parked, counts={}
    )

    assert ex == Exchange(kind="card_answer", said="no: not now", reply="Kept nothing.")


def test_the_exchange_of_a_finished_task_is_a_task_result() -> None:
    parked = pending_durable(task_id=TASK)

    ex = explore_exchange(
        state(pending_durable_call=parked),
        reply="The reduction is done.",
        parked=None,
        answered=parked,
        counts={},
    )

    assert ex == Exchange(kind="task_result", reply="The reduction is done.")


def test_the_delta_clears_the_answered_card() -> None:
    card = parked_approval(phase=EXPLORE_PHASE, tool_name="remember", **PREFERENCE_ARGS)
    held = state(pending_approval=card)

    delta = explore_state_delta(
        held, deps_of(held), parked=None, answered=card, spent=SpendMeter(), memories=[]
    )

    assert delta["pending_approval"] is None
    assert "pending_durable_call" not in delta


def test_the_delta_clears_a_card_a_typed_message_superseded() -> None:
    card = parked_approval(phase=EXPLORE_PHASE, tool_name="remember", **PREFERENCE_ARGS)
    held = state(pending_approval=card, user_prompt="What about orthologs?")

    delta = explore_state_delta(
        held, deps_of(held), parked=None, answered=None, spent=SpendMeter(), memories=[]
    )

    assert {key: delta[key] for key in delta if key.startswith("pending")} == {
        "pending_approval": None
    }


def test_the_delta_parks_the_new_card() -> None:
    held = state(user_prompt=EXPLORE_PROMPT)
    park = readings_park(FIRST_LABEL, SECOND_LABEL)

    delta = explore_state_delta(
        held, deps_of(held), parked=park, answered=None, spent=SpendMeter(), memories=[]
    )

    assert delta["pending_approval"] == park
    assert "pending_durable_call" not in delta


def test_the_delta_clears_the_answered_task_and_keeps_a_running_one() -> None:
    task = pending_durable(task_id=TASK)
    answered_state = state(pending_durable_call=task)
    running_state = state(pending_durable_call=task, user_prompt=EXPLORE_PROMPT)

    answered = explore_state_delta(
        answered_state,
        deps_of(answered_state),
        parked=None,
        answered=task,
        spent=SpendMeter(),
        memories=[],
    )
    running = explore_state_delta(
        running_state,
        deps_of(running_state),
        parked=None,
        answered=None,
        spent=SpendMeter(),
        memories=[],
    )

    assert answered["pending_durable_call"] is None
    assert "pending_durable_call" not in running


def test_the_delta_adds_the_spend_to_the_turn() -> None:
    held = state(
        user_prompt=EXPLORE_PROMPT,
        turn_total_tokens=10,
        turn_total_cost_usd=Decimal("0.5"),
    )
    meter = SpendMeter(
        spent=[
            ModelSpend(tokens=7, cost_usd=Decimal("0.25"), paid_by=PaidBy.DEPLOYMENT)
        ]
    )

    delta = explore_state_delta(
        held, deps_of(held), parked=None, answered=None, spent=meter, memories=[]
    )

    assert (delta["turn_total_tokens"], delta["turn_total_cost_usd"]) == (
        17,
        Decimal("0.75"),
    )
    assert delta["domain"] is held.domain
    assert delta["retrieved_memories"] == []
