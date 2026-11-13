"""The tools the Lead reaches follow the turn's typed state, never its
classification."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from strategist.ai.lead.intent import IntentClassification, UserIntent
from strategist.ai.lead.intent_gate import BUILDING_TOOLS
from strategist.ai.lead.lead_agent import build_lead_agent
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.lead.turn_contract import LeadResponse
from strategist.domain.eda_thread import OpenEdaAnalysis
from strategist.tests.unit.ai.lead.conftest import (
    OfferedTools,
    lead_deps,
    pipeline_state,
)

_PROSE = "I can build that whenever you want."

# The building tools a fresh thread meets the preconditions of: nothing is
# built, so verification has nothing to check, no build failed and no EDA
# subset was counted.
UNLOCKED_ON_A_FRESH_THREAD = BUILDING_TOOLS - {
    "create_eda_step",
    "recover_failed_steps",
    "verify_strategy",
}


def _deps(prompt: str, classification: IntentClassification | None = None) -> LeadDeps:
    """A thread with one question open, so an answer classification answers it."""
    state = pipeline_state("tritrypdb", user_prompt=prompt)
    state.turn_markers.questions_at_arrival = ["Which organism?"]
    deps = lead_deps(state)
    if classification is not None:
        deps.intent = UserIntent(
            classification=classification, inferred_goal="what the user is working on"
        )
        state.turn_markers.intent_classified = True
    return deps


def _final_part(call_id: str = "call_final") -> ToolCallPart:
    return ToolCallPart(
        tool_name="final_result",
        args={"prose": _PROSE, "nextState": "await_user"},
        tool_call_id=call_id,
    )


def _scripted(
    seen: OfferedTools,
) -> Callable[[list[ModelMessage], AgentInfo], ModelResponse]:
    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        if seen.record(info) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="read_ledger_section",
                        args={"section": "frame"},
                        tool_call_id="call_read",
                    ),
                ],
            )
        return ModelResponse(parts=[_final_part()])

    return _fn


def _model(seen: OfferedTools) -> FunctionModel:
    return FunctionModel(_scripted(seen), model_name="scripted")


def _run(prompt: str, classification: IntentClassification | None) -> OfferedTools:
    seen = OfferedTools()
    agent = build_lead_agent()
    result = asyncio.run(
        agent.run(prompt, deps=_deps(prompt, classification), model=_model(seen))
    )
    assert isinstance(result.output, LeadResponse)
    return seen


def test_an_unclassified_turn_is_offered_the_gene_set_save_beside_remember() -> None:
    """The first step shows both ways to keep a set, so neither stands in for
    the other."""
    seen = _run("Save the 155 genes as a gene set called gametocyte candidates", None)

    assert {
        "save_gene_set",
        "list_gene_sets",
        "remember",
    } <= seen.steps[0]


@pytest.mark.parametrize("classification", [None, *IntentClassification])
def test_every_turn_is_offered_the_building_tools_its_state_meets(
    classification: IntentClassification | None,
) -> None:
    seen = _run("Find A. gambiae midgut proteases", classification)

    assert seen.steps[-1] & BUILDING_TOOLS == UNLOCKED_ON_A_FRESH_THREAD


def test_a_question_about_the_data_keeps_the_reads_an_answer_needs() -> None:
    seen = _run(
        "Which of these genes are kinases?",
        IntentClassification.FOLLOW_UP_QUESTION,
    )

    assert {"read_ledger_section", "get_live_strategy_state"} <= seen.steps[1]


@pytest.mark.usefixtures("recorded_site_organisms")
def test_a_context_statement_turn_answers_in_prose() -> None:
    seen = OfferedTools()
    prompt = "I'm investigating virulence factors in Leishmania major"
    result = asyncio.run(
        build_lead_agent().run(
            prompt,
            deps=_deps(prompt, IntentClassification.CONTEXT_STATEMENT),
            model=_model(seen),
        ),
    )

    assert isinstance(result.output, LeadResponse)
    assert result.output.prose == _PROSE


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
    deps = _deps(prompt, classification)
    deps.state.domain.open_eda_analysis = OpenEdaAnalysis(
        dataset_id="DS_70dd50fed7", analysis_id="an-1", subset_previewed=True
    )
    seen = OfferedTools()
    agent = build_lead_agent()
    result = asyncio.run(agent.run(prompt, deps=deps, model=_model(seen)))

    assert isinstance(result.output, LeadResponse)
    assert seen.steps[1] >= EDA_ROUTE_TOOLS


@pytest.mark.usefixtures("recorded_site_organisms")
@pytest.mark.parametrize("classification", list(IntentClassification))
def test_every_intent_can_read_a_gene_record(
    classification: IntentClassification,
) -> None:
    """A fact about a gene is read from its record on any turn that has one."""
    seen = _run("How many exons does TGME49_233460 have?", classification)

    assert "read_gene_record" in seen.steps[1]


_COUNT_QUESTION = "How many protein-coding genes does 3D7 have?"
_EXPLAIN_QUESTION = "What does PF3D7_0708400 do?"


def test_the_lead_is_listed_the_same_tools_on_every_step() -> None:
    """A gated tool stays listed, so no step rewrites the request."""
    prompt = (
        "Yes, rerun the differential expression and then create the strategy "
        "step from the genes that pass."
    )
    seen = OfferedTools()

    asyncio.run(
        build_lead_agent().run(
            prompt,
            deps=_deps(prompt, IntentClassification.EXTEND_STRATEGY),
            model=_model(seen),
        ),
    )

    assert len(set(seen.listed)) == 1
    assert set(seen.listed[0]) >= BUILDING_TOOLS


def test_the_pinned_instructions_stay_the_same_on_every_step() -> None:
    prompt = (
        "Yes, rerun the differential expression and then create the strategy "
        "step from the genes that pass."
    )
    pinned: list[str] = []
    scripted = _scripted(OfferedTools())

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        request = messages[-1]
        assert isinstance(request, ModelRequest)
        pinned.append(request.instructions or "")
        return scripted(messages, info)

    asyncio.run(
        build_lead_agent().run(
            prompt,
            deps=_deps(prompt, IntentClassification.EXTEND_STRATEGY),
            model=FunctionModel(_fn, model_name="scripted"),
        ),
    )

    assert len(pinned) == 2
    assert len(set(pinned)) == 1
