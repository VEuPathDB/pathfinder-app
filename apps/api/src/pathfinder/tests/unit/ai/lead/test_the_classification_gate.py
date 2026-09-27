"""The gate refuses an answer to nothing and a control the message does not
hold, and fails a call that repeats the one it just refused."""

from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import PendingApproval
from pydantic_ai.exceptions import ModelRetry, ToolFailed

from pathfinder.ai.lead.intent import (
    ClassifiedIntent,
    IntentClassification,
    NamedControls,
    UserIntent,
    nothing_to_answer_message,
)
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

ANSWER = UserIntent(
    classification=IntentClassification.CLARIFICATION_RESPONSE,
    inferred_goal="Use the two genes as positive controls.",
)
ATTACHED = (
    "Use these genes as my positive controls.\n"
    "Attached gene-ID list from controls.csv: PF3D7_0709000, PF3D7_1133400"
)
NO_QUESTION = (
    "No question of yours is open on this conversation and no card waits, so "
    "this message answers none. Classify it as what it asks for: one of "
    "new_strategy, extend_strategy, edit_strategy, follow_up_question, "
    "off_topic, context_statement, memory_request."
)


def _deps(prompt: str = ATTACHED) -> LeadDeps:
    return lead_deps(pipeline_state(user_prompt=prompt))


def _controls(*positives: str, negatives: tuple[str, ...] = ()) -> UserIntent:
    return UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="Save the researcher's positive controls.",
        named_controls=NamedControls(
            positive_ids=list(positives), negative_ids=list(negatives)
        ),
    )


async def test_an_answer_with_no_question_open_is_refused() -> None:
    deps = _deps()

    with pytest.raises(ModelRetry) as refused:
        await classify_user_intent(run_context_for(deps), ANSWER)

    assert str(refused.value) == NO_QUESTION == nothing_to_answer_message()
    assert deps.intent is None
    assert deps.state.turn_markers.intent_classified is False


async def test_an_answer_to_a_question_open_at_arrival_is_recorded() -> None:
    deps = _deps()
    deps.state.turn_markers.questions_at_arrival = ["Which study?"]

    returned = await classify_user_intent(run_context_for(deps), ANSWER)

    assert ClassifiedIntent.model_validate(
        returned.return_value
    ).intent.classification is (IntentClassification.CLARIFICATION_RESPONSE)
    assert deps.state.turn_markers.intent_classified is True


async def test_an_answer_to_a_waiting_card_is_recorded() -> None:
    deps = _deps()
    deps.state.pending_approval = PendingApproval(
        phase="lead",
        tool_call_id="call_card",
        tool_name="propose_changes",
        tool_args={},
        prior_messages_json="[]",
        user_message_id=uuid4(),
    )

    await classify_user_intent(run_context_for(deps), ANSWER)

    assert deps.intent == ANSWER


async def test_a_repeat_of_the_refused_call_fails_without_a_retry() -> None:
    deps = _deps()
    ctx = run_context_for(deps)

    with pytest.raises(ModelRetry):
        await classify_user_intent(ctx, ANSWER)
    with pytest.raises(ToolFailed) as failed:
        await classify_user_intent(ctx, ANSWER.model_copy())

    assert failed.value.message == (
        f"{NO_QUESTION}\n\nThis call repeats the one just refused, so it fails "
        "without a retry. Ask the researcher the question this refusal states, "
        "through consult_user."
    )


async def test_a_refused_call_with_one_argument_changed_is_retried() -> None:
    ctx = run_context_for(_deps())
    with pytest.raises(ModelRetry):
        await classify_user_intent(ctx, ANSWER)
    changed = ANSWER.model_copy(update={"inferred_goal": "Save the two genes."})

    with pytest.raises(ModelRetry) as refused:
        await classify_user_intent(ctx, changed)

    assert str(refused.value) == NO_QUESTION


async def test_an_accepted_call_clears_the_refused_one() -> None:
    deps = _deps()
    ctx = run_context_for(deps)
    with pytest.raises(ModelRetry):
        await classify_user_intent(ctx, ANSWER)

    await classify_user_intent(ctx, _controls("PF3D7_0709000"))

    assert deps.refused_classification is None


async def test_controls_the_attached_list_carries_are_recorded() -> None:
    deps = _deps()
    intent = _controls("PF3D7_0709000", "PF3D7_1133400")

    returned = await classify_user_intent(run_context_for(deps), intent)

    named = ClassifiedIntent.model_validate(returned.return_value).intent.named_controls
    assert named is not None
    assert named.positive_ids == ["PF3D7_0709000", "PF3D7_1133400"]
    assert deps.intent == intent


@pytest.mark.parametrize(
    ("positives", "negatives", "absent"),
    [
        (("PF3D7_0709000", "PF3D7_0213400"), (), "PF3D7_0213400"),
        (("PF3D7_0709",), (), "PF3D7_0709"),
        (("PF3D7_0709000",), ("PF3D7_1133400.1",), "PF3D7_1133400.1"),
    ],
)
async def test_a_control_the_message_does_not_hold_is_refused(
    positives: tuple[str, ...], negatives: tuple[str, ...], absent: str
) -> None:
    deps = _deps()

    with pytest.raises(ModelRetry) as refused:
        await classify_user_intent(
            run_context_for(deps), _controls(*positives, negatives=negatives)
        )

    assert str(refused.value) == (
        f"The researcher's message does not hold {absent}. Name as controls only "
        "the ids the message types or attaches, spelled as it spells them."
    )
    assert deps.intent is None
