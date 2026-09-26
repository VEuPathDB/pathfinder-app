"""The Lead agent: what the factory builds, and what its contract refuses."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from assistant_core.memory.schemas import MemoryValue
from assistant_core.models.settings import baked_model_id
from pydantic_ai import DeferredToolRequests, RunContext
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.usage import RunUsage

from pathfinder.ai.agents._instructions import pinned_user_memories
from pathfinder.ai.graph import lead_node
from pathfinder.ai.graph.lead_node import make_lead_node
from pathfinder.ai.lead import lead_agent
from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.guarantees import registered_tools
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.lead_agent import LEAD_MODEL, build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.tests._support.instructions import pinned_instructions
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    RetryRecordingScript,
    lead_deps,
    pipeline_state,
    user_intent,
)

# Every tool the Lead registers, across its own list and the toolsets it
# mounts: the EDA seven and the sweep's own enum-constrained toolset.
LEAD_TOOL_NAMES = frozenset(
    {
        "build_control_set",
        "build_strategy",
        "classify_user_intent",
        "clear_strategy",
        "compare_search_variants",
        "compare_variants_scored",
        "consult_user",
        "delete_step",
        "edit_strategy",
        "export_gene_set",
        "frame_problem",
        "get_live_strategy_state",
        "list_control_sets",
        "list_gene_sets",
        "optimize_search_parameters",
        "read_control_set",
        "read_gene_ids_from_gene_set",
        "read_gene_ids_from_strategy",
        "read_gene_record",
        "read_ledger_section",
        "recover_failed_steps",
        "remember",
        "rename_strategy",
        "save_gene_set",
        "verify_strategy",
        "search_eda_studies",
        "describe_eda_study",
        "open_eda_analysis",
        "set_eda_filters",
        "preview_eda_subset",
        "run_eda_compute",
        "create_eda_step",
        "propose_changes",
        "separate_controls",
        "adopt_separating_strategy",
    }
)

PINNED_INSTRUCTIONS = [
    "pinned_user_memories",
    "pinned_user_prompt",
    "pinned_user_intent",
    "pinned_operational_spec",
    "pinned_eda_sheet",
    "pinned_ledger_summary",
    "pinned_run_budget",
    "pinned_machine_guarantees",
    "pinned_turn_briefing",
]

_NUDGE_PROMPT = "Export the heat-shock genes as a step"
_NUDGE_PROSE = "I added the step."


def test_the_lead_module_owns_no_agent_singleton() -> None:
    assert "lead_agent" not in vars(lead_agent)


def test_the_turn_node_owns_no_agent_singleton() -> None:
    assert "lead_agent" not in vars(lead_node)


def test_each_build_returns_its_own_agent() -> None:
    assert build_lead_agent() is not build_lead_agent()


def test_the_built_agent_carries_every_lead_tool() -> None:
    assert set(registered_tools(build_lead_agent().toolsets)) == LEAD_TOOL_NAMES


def test_the_tools_that_ask_for_approval() -> None:
    """The seven the user answers: a design fork, two offers of further work,
    two deletions, a long sweep and a long separation run."""
    tools = registered_tools(build_lead_agent().toolsets)
    deferred = sorted(name for name, tool in tools.items() if tool.requires_approval)
    assert deferred == [
        "adopt_separating_strategy",
        "clear_strategy",
        "consult_user",
        "delete_step",
        "optimize_search_parameters",
        "propose_changes",
        "separate_controls",
    ]


def test_the_built_agent_keeps_its_model_and_identity() -> None:
    agent = build_lead_agent()
    assert baked_model_id(agent) == LEAD_MODEL
    assert agent.name == "lead"


def test_the_built_agent_pins_the_same_instructions_in_the_same_order() -> None:
    instructions = pinned_instructions(build_lead_agent())
    assert instructions[0] == LEAD_INSTRUCTIONS
    assert instructions[1:] == PINNED_INSTRUCTIONS


def test_the_node_factory_takes_the_agent_factory() -> None:
    params = inspect.signature(make_lead_node).parameters
    assert "build_agent" in params
    assert params["build_agent"].default is inspect.Parameter.empty


def test_the_lead_renders_the_memories_its_turn_retrieved() -> None:
    """Memories reach the Lead, and the render reads its deps."""
    memory = MemoryValue(
        kind="preference",
        name="preferred_dataset",
        summary="Prefers the Su et al. strand-specific dataset",
        content={},
        created_at=datetime.now(UTC),
    )
    deps = lead_deps(pipeline_state())
    deps.retrieved_memories = [memory]
    ctx = RunContext(deps=deps, model=TestModel(), usage=RunUsage())

    rendered = pinned_user_memories(ctx)

    assert rendered is not None
    assert "Prefers the Su et al. strand-specific dataset" in rendered
    assert (
        pinned_user_memories(
            RunContext(
                deps=lead_deps(pipeline_state()), model=TestModel(), usage=RunUsage()
            )
        )
        is None
    )


def _nudge_deps(
    *,
    built: bool,
    verified: bool = False,
    dispatched: bool = False,
) -> LeadDeps:
    state = pipeline_state(user_prompt=_NUDGE_PROMPT, user_message_id=uuid4())
    state.turn_markers.intent_classified = True
    if built:
        state.record_build(BuildOutcome(pushed_step_ids=["step_1"], root_count=1543))
    state.turn_markers.verified = verified
    state.turn_markers.verification_dispatched = dispatched
    return lead_deps(
        state,
        intent=user_intent(
            IntentClassification.EXTEND_STRATEGY,
            inferred_goal="export the subset",
        ),
    )


def _answering_script(deps: LeadDeps) -> RetryRecordingScript:
    """An answer that reports the change the turn made, so only the
    verification nudge can refuse it."""
    return RetryRecordingScript(
        ToolCallPart(
            tool_name="final_result",
            args={
                "prose": _NUDGE_PROSE,
                "nextState": "await_user",
                "strategyChanged": deps.state.turn_markers.changed_strategy,
            },
            tool_call_id="call_final",
        ),
    )


def _parking_script() -> RetryRecordingScript:
    return RetryRecordingScript(
        ToolCallPart(
            tool_name="consult_user",
            args={
                "questions": [{"id": "q1", "prompt": "Which arm should I add?"}],
                "reply": "Two arms fit the request, and the choice changes the steps.",
            },
            tool_call_id="call_consult",
        ),
    )


def _run(deps: LeadDeps) -> RetryRecordingScript:
    script = _answering_script(deps)
    result = asyncio.run(
        build_lead_agent().run(_NUDGE_PROMPT, deps=deps, model=script.model()),
    )
    assert isinstance(result.output, LeadResponse)
    assert result.output.prose == _NUDGE_PROSE
    return script


def test_a_built_turn_that_never_verified_is_asked_once() -> None:
    deps = _nudge_deps(built=True)

    script = _run(deps)

    assert len(script.retries) == 1
    assert "verify_strategy" in script.retries[0]
    assert "1 step(s) on VEuPathDB" in script.retries[0]
    assert "root count 1543" in script.retries[0]
    assert deps.state.turn_markers.contract_refused is True


def test_the_second_answer_goes_through_even_when_it_still_declines() -> None:
    """The nudge compels the attempt, not the outcome."""
    assert len(_run(_nudge_deps(built=True)).retries) == 1


def test_a_verified_turn_is_never_asked() -> None:
    deps = _nudge_deps(built=True, verified=True)

    assert _run(deps).retries == []
    assert deps.state.turn_markers.contract_refused is False


def test_a_verification_that_ran_and_failed_is_never_asked_again() -> None:
    """A dispatch that reported failure already checked the build."""
    assert _run(_nudge_deps(built=True, dispatched=True)).retries == []


def test_a_turn_that_built_nothing_is_never_asked() -> None:
    assert _run(_nudge_deps(built=False)).retries == []


def test_a_card_turn_that_owes_nothing_parks_unasked() -> None:
    """The text beside a card is held to the turn's record, and this one passes."""
    deps = _nudge_deps(built=False)
    script = _parking_script()

    result = asyncio.run(
        build_lead_agent().run(_NUDGE_PROMPT, deps=deps, model=script.model()),
    )

    assert isinstance(result.output, DeferredToolRequests)
    assert [call.tool_name for call in result.output.approvals] == ["consult_user"]
    assert deps.state.turn_markers.contract_refused is False


def test_a_built_card_turn_that_never_verified_is_asked_once() -> None:
    """The card is denied with the correction once, and the next card parks."""
    deps = _nudge_deps(built=True)
    script = _parking_script()

    result = asyncio.run(
        build_lead_agent().run(_NUDGE_PROMPT, deps=deps, model=script.model()),
    )

    assert isinstance(result.output, DeferredToolRequests)
    assert [call.tool_name for call in result.output.approvals] == ["consult_user"]
    assert deps.state.turn_markers.contract_refused is True


_SERVED_PAPER = (
    '{"query": "SRS29B", "results": [{"title": "SAG1-related sequences", '
    '"doi": "10.1016/j.molbiopara.2006.01.001", "pmid": null, "url": null}], '
    '"sources": [], "sourcesStatus": [], "guidance": ""}'
)


async def test_the_turn_sources_record_what_they_return() -> None:
    """A served answer reaches the turn's markers through the recorder."""
    inner: FunctionToolset[object] = FunctionToolset()

    def literature(query: str) -> str:
        del query
        return _SERVED_PAPER

    inner.add_function(literature, name="research_literature_search")
    deps = lead_deps(pipeline_state(user_prompt="q"))
    deps.runtime = replace(deps.runtime, tool_sources={"research": inner})
    ctx = run_context_for(deps, tool_call_id="call_lit")
    sources = lead_agent.turn_tool_sources(ctx)
    assert sources is not None
    tools = await sources.get_tools(ctx)

    answer = await sources.call_tool(
        "research_literature_search",
        {"query": "SRS29B"},
        ctx,
        tools["research_literature_search"],
    )

    assert answer == _SERVED_PAPER
    assert deps.state.turn_markers.retrieved_sources == [
        "10.1016/j.molbiopara.2006.01.001",
    ]


def test_a_turn_with_no_sources_offers_no_source_tools() -> None:
    ctx = run_context_for(lead_deps(pipeline_state(user_prompt="q")))

    assert [lead_agent.turn_tool_sources(ctx)] == [None]
