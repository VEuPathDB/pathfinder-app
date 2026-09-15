"""The Lead sees the building tools only when this turn's intent asks to build.

A context statement and a memory request are answered in prose; the tools that
change a strategy are not on the model's list for those turns.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.intent_gate import BUILDING_TOOLS
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.domain.eda_thread import OpenEdaAnalysis
from pathfinder.tests.unit.ai.lead.conftest import (
    OfferedTools,
    lead_deps,
    pipeline_state,
)

_PROSE = "I can build that whenever you want. Want me to?"

# The building tools a fresh thread meets the preconditions of: nothing is
# built, so verification has nothing to check, no build failed and no EDA
# subset was counted.
UNLOCKED_ON_A_FRESH_THREAD = BUILDING_TOOLS - {
    "create_eda_step",
    "recover_failed_steps",
    "verify_strategy",
}


def _deps(prompt: str) -> LeadDeps:
    return lead_deps(pipeline_state("tritrypdb", user_prompt=prompt))


def _classify_args(classification: IntentClassification) -> dict[str, Any]:
    return {
        "intent": {
            "classification": classification.value,
            "inferredGoal": "what the user is working on",
        },
    }


def _final_part(call_id: str = "call_final") -> ToolCallPart:
    return ToolCallPart(
        tool_name="final_result",
        args={"prose": _PROSE, "nextState": "await_user", "strategyChanged": False},
        tool_call_id=call_id,
    )


def _model(
    prompt: str,
    classification: IntentClassification | None,
    seen: OfferedTools,
) -> FunctionModel:
    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        step = seen.record(info)
        if classification is not None and step == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="classify_user_intent",
                        args=_classify_args(classification),
                        tool_call_id="call_classify",
                    ),
                ],
            )
        return ModelResponse(parts=[_final_part()])

    return FunctionModel(_fn, model_name="scripted")


def _run(prompt: str, classification: IntentClassification | None) -> OfferedTools:
    seen = OfferedTools()
    agent = build_lead_agent()
    result = asyncio.run(
        agent.run(
            prompt, deps=_deps(prompt), model=_model(prompt, classification, seen)
        )
    )
    assert isinstance(result.output, LeadResponse)
    return seen


def test_an_unclassified_turn_is_offered_no_building_tool() -> None:
    seen = _run("I'm investigating virulence factors in Leishmania major", None)

    assert seen.steps
    assert not (seen.steps[0] & BUILDING_TOOLS)
    assert "classify_user_intent" in seen.steps[0]


def test_an_unclassified_turn_is_offered_the_workbench_save_beside_remember() -> None:
    """The first step shows both ways to keep a set, so neither stands in for
    the other."""
    seen = _run("Save the 155 genes as a gene set called gametocyte candidates", None)

    assert {
        "create_workbench_gene_set",
        "list_workbench_gene_sets",
        "remember",
    } <= seen.steps[0]


def test_a_context_statement_is_offered_no_building_tool() -> None:
    seen = _run(
        "I'm investigating virulence factors in Leishmania major",
        IntentClassification.CONTEXT_STATEMENT,
    )

    assert len(seen.steps) == 2
    assert not (seen.steps[1] & BUILDING_TOOLS)
    assert {"get_live_strategy_state", "read_ledger_section", "remember"} <= (
        seen.steps[1]
    )


def test_a_memory_request_keeps_remember_and_hides_the_building_tools() -> None:
    seen = _run(
        "Please remember for future sessions that I work on P. falciparum 3D7.",
        IntentClassification.MEMORY_REQUEST,
    )

    assert "remember" in seen.steps[1]
    assert "frame_problem" not in seen.steps[1]
    assert "build_strategy" not in seen.steps[1]
    assert "run_eda_compute" not in seen.steps[1]


@pytest.mark.parametrize(
    "classification",
    [
        IntentClassification.NEW_STRATEGY,
        IntentClassification.EXTEND_STRATEGY,
        IntentClassification.EDIT_STRATEGY,
        IntentClassification.CLARIFICATION_RESPONSE,
        IntentClassification.SLOT_ANSWER,
        IntentClassification.APPROVAL,
    ],
)
def test_an_intent_that_builds_is_offered_every_building_tool(
    classification: IntentClassification,
) -> None:
    seen = _run("Find A. gambiae midgut proteases", classification)

    assert seen.steps[1] >= UNLOCKED_ON_A_FRESH_THREAD


@pytest.mark.parametrize(
    "classification",
    [
        IntentClassification.FOLLOW_UP_QUESTION,
        IntentClassification.OFF_TOPIC,
        IntentClassification.DENIAL,
    ],
)
def test_an_intent_that_does_not_build_is_offered_none_of_them(
    classification: IntentClassification,
) -> None:
    seen = _run("What does that step do?", classification)

    assert not (seen.steps[1] & BUILDING_TOOLS)


def test_an_off_topic_turn_is_offered_no_tool_at_all() -> None:
    """The reply is the redirect, so nothing the Lead could call is listed."""
    seen = _run(
        "Write me a Python script that reverses a linked list.",
        IntentClassification.OFF_TOPIC,
    )

    assert seen.steps[1] == frozenset()


def test_a_question_about_the_data_keeps_the_reads_an_answer_needs() -> None:
    seen = _run(
        "Which of these genes are kinases?",
        IntentClassification.FOLLOW_UP_QUESTION,
    )

    assert {"read_ledger_section", "get_live_strategy_state"} <= seen.steps[1]


def test_a_context_statement_turn_answers_in_prose() -> None:
    seen = OfferedTools()
    prompt = "I'm investigating virulence factors in Leishmania major"
    result = asyncio.run(
        build_lead_agent().run(
            prompt,
            deps=_deps(prompt),
            model=_model(prompt, IntentClassification.CONTEXT_STATEMENT, seen),
        ),
    )

    assert isinstance(result.output, LeadResponse)
    assert result.output.prose == _PROSE


def _reclassifying_model(prompt: str, seen: OfferedTools) -> FunctionModel:
    """A turn that classifies a build as a question, then corrects itself."""
    scripted = {
        1: IntentClassification.FOLLOW_UP_QUESTION,
        2: IntentClassification.EXTEND_STRATEGY,
    }

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        step = seen.record(info)
        classification = scripted.get(step)
        if classification is None:
            return ModelResponse(parts=[_final_part()])
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="classify_user_intent",
                    args=_classify_args(classification),
                    tool_call_id=f"call_{step}",
                ),
            ],
        )

    return FunctionModel(_fn, model_name="scripted")


def test_a_corrected_classification_unhides_the_building_tools() -> None:
    """A misclassified build degrades to one wasted step, not to a refusal."""
    prompt = (
        "Yes, rerun the differential expression and then create the strategy "
        "step from the genes that pass."
    )
    seen = OfferedTools()
    result = asyncio.run(
        build_lead_agent().run(
            prompt,
            deps=_deps(prompt),
            model=_reclassifying_model(prompt, seen),
        ),
    )

    assert isinstance(result.output, LeadResponse)
    assert len(seen.steps) == 3
    assert not (seen.steps[1] & BUILDING_TOOLS)
    assert seen.steps[2] >= UNLOCKED_ON_A_FRESH_THREAD
    assert {"build_strategy", "edit_strategy"} <= seen.steps[2]


# The four calls that build an EDA-backed criterion, in the order the route
# runs them.
EDA_ROUTE_TOOLS = frozenset(
    {
        "open_eda_analysis",
        "set_eda_filters",
        "preview_eda_subset",
        "create_eda_step",
    }
)


@pytest.mark.parametrize(
    "classification",
    [
        IntentClassification.NEW_STRATEGY,
        IntentClassification.EXTEND_STRATEGY,
        IntentClassification.EDIT_STRATEGY,
    ],
)
def test_every_building_intent_is_offered_the_whole_eda_route(
    classification: IntentClassification,
) -> None:
    """An EDA-backed criterion is built by these four, whatever the request is."""
    prompt = "Genes essential in blood stages"
    deps = _deps(prompt)
    deps.state.domain.open_eda_analysis = OpenEdaAnalysis(
        dataset_id="DS_70dd50fed7", analysis_id="an-1", subset_previewed=True
    )
    seen = OfferedTools()
    agent = build_lead_agent()
    result = asyncio.run(
        agent.run(prompt, deps=deps, model=_model(prompt, classification, seen))
    )

    assert isinstance(result.output, LeadResponse)
    assert seen.steps[1] >= EDA_ROUTE_TOOLS
