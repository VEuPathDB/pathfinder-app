"""A turn PathFinder does no part of is classified, redirected and ended.

The scripted model drives the real Lead agent, so the tool list, the pins and
the turn contract are the ones a served turn runs under.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic_ai.messages import ModelResponse, ToolCallPart

from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import (
    OFF_TOPIC_REPLY_MAX_CHARS,
    LeadResponse,
)
from pathfinder.ai.models.mock import get_mock_model
from pathfinder.ai.models.mock.prose_arcs import KINASE_PROSE, OFF_TOPIC_PROSE
from pathfinder.tests._support.run_context import turn_runtime
from pathfinder.tests.unit.ai.lead.conftest import session_with_one_step

_OFF_TOPIC = "Write me a Python script that reverses a linked list."
_BIOLOGY = "Which of these genes are kinases?"


def _deps(prompt: str, *, built: bool) -> LeadDeps:
    session = session_with_one_step() if built else None
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt=prompt,
        user_message_id=uuid4(),
        domain=StrategyDomainState(
            turn_briefing="## Since your last turn\n- a strategy was built",
        ),
    )
    return LeadDeps(
        state=state,
        intent=None,
        runtime=turn_runtime(user_id=state.user_id, strategy_session=session),
        retrieved_memories=[],
    )


async def _run(prompt: str, *, built: bool) -> tuple[LeadResponse, list[str], LeadDeps]:
    deps = _deps(prompt, built=built)
    result = await build_lead_agent().run(prompt, deps=deps, model=get_mock_model())
    assert isinstance(result.output, LeadResponse)
    called = [
        part.tool_name
        for message in result.all_messages()
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    ]
    return result.output, called, deps


async def test_an_off_topic_turn_classifies_then_answers_and_calls_nothing_else(
    postgres_container: object,
) -> None:
    del postgres_container
    output, called, deps = await _run(_OFF_TOPIC, built=False)

    assert called == ["classify_user_intent", "final_result"]
    assert deps.intent is not None
    assert deps.intent.classification is IntentClassification.OFF_TOPIC
    assert output.prose == OFF_TOPIC_PROSE


async def test_the_off_topic_reply_is_short_and_names_what_pathfinder_does(
    postgres_container: object,
) -> None:
    del postgres_container
    output, _, _ = await _run(_OFF_TOPIC, built=False)

    assert "```" not in output.prose
    assert len(output.prose) < OFF_TOPIC_REPLY_MAX_CHARS
    assert "VEuPathDB" in output.prose
    assert "EDA" in output.prose


async def test_a_biology_question_after_a_build_is_not_off_topic(
    postgres_container: object,
) -> None:
    """The redirect never fires on a question about the genes on the thread."""
    del postgres_container
    output, called, deps = await _run(_BIOLOGY, built=True)

    assert called == ["classify_user_intent", "final_result"]
    assert deps.intent is not None
    assert deps.intent.classification is IntentClassification.FOLLOW_UP_QUESTION
    assert output.prose == KINASE_PROSE
    assert output.prose != OFF_TOPIC_PROSE
