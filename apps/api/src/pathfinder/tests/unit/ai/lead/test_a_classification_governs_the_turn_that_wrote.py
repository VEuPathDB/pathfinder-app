"""A turn keeps the classification that did its work, and its repeats spend nothing.

A repeated classification fails without a retry, a change of classification
after the turn wrote is refused, a turn that built keeps its check, and a record
the Lead reads again does not reach the site.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic_ai.exceptions import ToolFailed
from pydantic_ai.messages import (
    ModelMessage,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)

from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.intent_gate import BUILDING_TOOLS, tools_the_turn_offers
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.ai.models.mock import get_mock_model
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.services.gene_records import read
from pathfinder.services.gene_records.read import GeneRecordSummary
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    final_result_part,
    lead_deps,
    pipeline_state,
    session_with_one_step,
    tool_script_model,
    user_intent,
)

# The fifth turn of the microsporidiadb polar tube conversation.
_POLAR_TUBE_T5 = (
    "Keep the product-field search as my strategy. Separately, just to answer "
    "my question, run the exact phrase and tell me which genes it matches "
    "beyond EBI_26400, without changing the strategy."
)

pytestmark = pytest.mark.usefixtures("recorded_site_organisms")


def _classify_args(classification: IntentClassification, goal: str) -> dict[str, Any]:
    return {
        "intent": {"classification": classification.value, "inferredGoal": goal},
    }


async def test_a_repeated_classification_fails_without_a_retry() -> None:
    state = pipeline_state("microsporidiadb", user_prompt=_POLAR_TUBE_T5)
    ctx = run_context_for(lead_deps(state), tool_call_id="call_classify")
    question = user_intent(IntentClassification.FOLLOW_UP_QUESTION)
    await classify_user_intent(ctx, question)

    with pytest.raises(ToolFailed) as refused:
        await classify_user_intent(ctx, question)

    assert "already classified as follow_up_question" in refused.value.message


def test_four_repeated_classifications_leave_the_turn_its_answer() -> None:
    """The fifth call of one classification still ends on the Lead's reply."""
    classify = IntentClassification.FOLLOW_UP_QUESTION

    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        if len(messages) > 10:
            return final_result_part(
                {
                    "prose": "The phrase matches the one gene shown.",
                    "nextState": "complete",
                    "strategyChanged": False,
                }
            )
        return ToolCallPart(
            tool_name="classify_user_intent",
            args=_classify_args(
                classify, f"the genes the phrase matches ({len(messages)})"
            ),
            tool_call_id=f"call_classify_{len(messages)}",
        )

    state = pipeline_state("microsporidiadb", user_prompt=_POLAR_TUBE_T5)
    result = asyncio.run(
        build_lead_agent().run(
            _POLAR_TUBE_T5,
            deps=lead_deps(state),
            model=tool_script_model(_part),
        )
    )

    assert isinstance(result.output, LeadResponse)
    assert result.output.prose == "The phrase matches the one gene shown."


async def test_the_reclassified_arc_on_the_real_lead_ends_on_its_answer() -> None:
    """Five classifications on the mock model spend no retry, and the turn answers."""
    prompt = f"{_POLAR_TUBE_T5} [[arc:reclassified]]"
    bind_scripted_scope("microsporidiadb", prompt)
    state = pipeline_state("microsporidiadb", user_prompt=prompt)

    result = await build_lead_agent().run(
        prompt, deps=lead_deps(state), model=get_mock_model()
    )

    answers = [
        part.outcome if isinstance(part, ToolReturnPart) else "retry"
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart | RetryPromptPart)
        and part.tool_name == "classify_user_intent"
    ]
    assert isinstance(result.output, LeadResponse)
    assert answers == ["success", *["failed"] * 4]


@pytest.mark.parametrize("wrote", ["built", "edited"])
async def test_a_reclassification_after_the_turn_wrote_is_refused(wrote: str) -> None:
    state = pipeline_state("hostdb", user_prompt="Mus musculus genes on chromosome 17")
    ctx = run_context_for(lead_deps(state), tool_call_id="call_classify")
    first = user_intent(IntentClassification.NEW_STRATEGY)
    await classify_user_intent(ctx, first)
    setattr(state.turn_markers, wrote, True)

    with pytest.raises(ToolFailed) as refused:
        await classify_user_intent(
            ctx, user_intent(IntentClassification.EXTEND_STRATEGY)
        )

    assert "new_strategy" in refused.value.message
    assert "changed the strategy" in refused.value.message
    assert ctx.deps.intent is first


def test_a_turn_that_built_keeps_its_check_under_a_question_classification() -> None:
    state = pipeline_state("microsporidiadb", user_prompt=_POLAR_TUBE_T5)
    state.turn_markers.intent_classified = True
    state.turn_markers.built = True
    deps = lead_deps(
        state,
        intent=user_intent(IntentClassification.FOLLOW_UP_QUESTION),
        strategy_session=session_with_one_step("microsporidiadb"),
    )

    assert "verify_strategy" in tools_the_turn_offers(deps, BUILDING_TOOLS)


async def test_the_read_again_arc_on_the_real_lead_reads_each_record_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each record the arc reads twice reaches the site once."""
    asked: list[str] = []

    async def _read(
        site_id: str, gene_id: str, *, ortholog_organism: str | None = None
    ) -> GeneRecordSummary:
        del ortholog_organism
        asked.append(gene_id)
        return GeneRecordSummary(
            site_id=site_id,
            gene_id=gene_id,
            record_url=f"https://qa.plasmodb.org/plasmo.qa/app/record/gene/{gene_id}",
        )

    monkeypatch.setattr(read, "read_gene_record", _read)
    prompt = "List those genes again [[arc:read-again]]"
    bind_scripted_scope("plasmodb", prompt)
    state = pipeline_state("plasmodb", user_prompt=prompt)

    result = await build_lead_agent().run(
        prompt, deps=lead_deps(state), model=get_mock_model()
    )

    shown = list(SiteValues.for_site("plasmodb").controls.positive_ids[:3])
    outcomes = [
        part.outcome
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "read_gene_record"
    ]
    assert isinstance(result.output, LeadResponse)
    assert (asked, outcomes) == (shown, [*["success"] * 3, *["failed"] * 3])
