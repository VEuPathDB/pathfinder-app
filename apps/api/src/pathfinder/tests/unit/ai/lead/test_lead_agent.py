"""The Lead agent: what the factory builds, and what its contract refuses."""

from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime
from uuid import uuid4

from assistant_core.memory.schemas import MemoryValue
from assistant_core.models.settings import baked_model_id
from pydantic_ai import DeferredToolRequests, RunContext
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from pathfinder.ai.agents._instructions import pinned_user_memories
from pathfinder.ai.graph import lead_node
from pathfinder.ai.graph.lead_node import make_lead_node
from pathfinder.ai.lead import lead_agent
from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.lead_agent import LEAD_MODEL, build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.tests._support.instructions import pinned_instructions
from pathfinder.tests.unit.ai.lead.conftest import (
    RetryRecordingScript,
    lead_deps,
    pipeline_state,
    user_intent,
)

LEAD_TOOL_NAMES = frozenset(
    {
        "build_control_set",
        "build_strategy",
        "classify_user_intent",
        "clear_strategy",
        "compare_search_variants",
        "compare_variants_scored",
        "consult_user",
        "create_workbench_gene_set",
        "delete_step",
        "edit_strategy",
        "export_gene_set",
        "frame_problem",
        "get_live_strategy_state",
        "import_control_ids_from_gene_set",
        "import_control_ids_from_strategy",
        "list_control_sets",
        "list_workbench_gene_sets",
        "read_gene_record",
        "read_ledger_section",
        "recover_failed_steps",
        "remember",
        "run_gene_set_enrichment",
        "verify_strategy",
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
    assert set(build_lead_agent()._function_toolset.tools) == LEAD_TOOL_NAMES


def test_the_tools_that_ask_for_approval() -> None:
    """The three tools the user answers: a design fork and two deletions."""
    tools = build_lead_agent()._function_toolset.tools
    deferred = sorted(name for name, tool in tools.items() if tool.requires_approval)
    assert deferred == ["clear_strategy", "consult_user", "delete_step"]


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
            args={"questions": [{"id": "q1", "prompt": "Which arm should I add?"}]},
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


def test_a_turn_that_parks_on_an_approval_is_never_asked() -> None:
    """A parked turn has not answered yet, so there is nothing to refuse."""
    deps = _nudge_deps(built=True)
    script = _parking_script()

    result = asyncio.run(
        build_lead_agent().run(_NUDGE_PROMPT, deps=deps, model=script.model()),
    )

    assert isinstance(result.output, DeferredToolRequests)
    assert script.retries == []
    assert deps.state.turn_markers.contract_refused is False
