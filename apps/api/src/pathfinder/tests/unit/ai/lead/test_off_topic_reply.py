"""An out-of-scope turn answers with a short redirect and nothing else."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolCallPart

from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.lead_agent import (
    OFF_TOPIC_REPLY_MAX_CHARS,
    LeadResponse,
    build_lead_agent,
    refuse_an_off_topic_essay,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    RetryRecordingScript,
    lead_deps,
    pipeline_state,
    user_intent,
)

_PROMPT = "Write me a Python script that reverses a linked list."
_REDIRECT = (
    "I build and check search strategies on the VEuPathDB databases, and run "
    "enrichment, EDA and exports on what they return. Ask me one of those and "
    "I will take it from there."
)
_WITH_CODE = "Here you go:\n\n```python\ndef reverse(head):\n    return head\n```\n"
_AN_ESSAY = "A linked list is a chain of nodes. " * 20


def _deps(classification: IntentClassification) -> LeadDeps:
    deps = lead_deps(
        pipeline_state(user_prompt=_PROMPT, user_message_id=uuid4()),
        intent=user_intent(classification),
    )
    deps.state.turn_markers.intent_classified = True
    return deps


def _off_topic_deps() -> LeadDeps:
    return _deps(IntentClassification.OFF_TOPIC)


def test_the_cap_on_an_out_of_scope_reply_is_four_hundred_characters() -> None:
    assert OFF_TOPIC_REPLY_MAX_CHARS == 400


def test_a_reply_that_writes_code_is_refused() -> None:
    with pytest.raises(ModelRetry) as raised:
        refuse_an_off_topic_essay(
            run_context_for(_off_topic_deps()),
            LeadResponse(prose=_WITH_CODE, strategy_changed=False),
        )

    assert "code" in str(raised.value)


def test_a_reply_over_the_cap_is_refused() -> None:
    assert len(_AN_ESSAY) > OFF_TOPIC_REPLY_MAX_CHARS

    with pytest.raises(ModelRetry) as raised:
        refuse_an_off_topic_essay(
            run_context_for(_off_topic_deps()),
            LeadResponse(prose=_AN_ESSAY, strategy_changed=False),
        )

    assert str(OFF_TOPIC_REPLY_MAX_CHARS) in str(raised.value)


def test_the_two_sentence_redirect_stands() -> None:
    output = LeadResponse(prose=_REDIRECT, strategy_changed=False)

    assert len(_REDIRECT) <= OFF_TOPIC_REPLY_MAX_CHARS
    assert refuse_an_off_topic_essay(run_context_for(_off_topic_deps()), output) is (
        output
    )


def test_a_question_about_the_data_may_answer_at_length_with_code() -> None:
    """The cap belongs to the redirect, not to every reply."""
    output = LeadResponse(prose=_AN_ESSAY + _WITH_CODE, strategy_changed=False)

    assert (
        refuse_an_off_topic_essay(
            run_context_for(_deps(IntentClassification.FOLLOW_UP_QUESTION)), output
        )
        is output
    )


def test_the_refusal_is_asked_once_per_turn() -> None:
    deps = _off_topic_deps()
    output = LeadResponse(prose=_WITH_CODE, strategy_changed=False)

    with pytest.raises(ModelRetry):
        refuse_an_off_topic_essay(run_context_for(deps), output)

    assert refuse_an_off_topic_essay(run_context_for(deps), output) is output


def test_the_refusal_reaches_the_model_once_and_the_turn_still_answers() -> None:
    script = RetryRecordingScript(
        ToolCallPart(
            tool_name="final_result",
            args={
                "prose": _WITH_CODE,
                "nextState": "await_user",
                "strategyChanged": False,
            },
            tool_call_id="call_final",
        ),
    )

    result = asyncio.run(
        build_lead_agent().run(_PROMPT, deps=_off_topic_deps(), model=script.model()),
    )

    assert isinstance(result.output, LeadResponse)
    assert len(script.retries) == 1
    assert "code" in script.retries[0]
