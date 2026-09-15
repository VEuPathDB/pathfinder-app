"""The Lead agent, which owns the user-facing voice and calls the sub-agent tools.

The Lead reads the typed ledger after each call and decides the next tool. A phase is
a tool the Lead invokes, not a node in a fixed graph.
"""

from __future__ import annotations

from typing import Any

from assistant_core.conversation.history import HISTORY_PROCESSORS
from pydantic_ai import Agent, DeferredToolRequests, RunContext, Tool
from pydantic_ai.capabilities import PrepareTools, ProcessHistory, Thinking
from pydantic_ai.toolsets import AbstractToolset

from pathfinder.ai.agents._instructions import (
    pinned_run_budget,
    pinned_user_memories,
)
from pathfinder.ai.graph.runtime import one_toolset
from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.edit_dispatch import edit_strategy
from pathfinder.ai.lead.frame_dispatch import frame_problem
from pathfinder.ai.lead.guarantees import machine_guarantees_pin
from pathfinder.ai.lead.intent_gate import apply_tool_preconditions
from pathfinder.ai.lead.lead_consult import consult_user
from pathfinder.ai.lead.lead_pins import (
    pinned_eda_sheet,
    pinned_ledger_summary,
    pinned_operational_spec,
    pinned_turn_briefing,
    pinned_user_intent,
    pinned_user_prompt,
)
from pathfinder.ai.lead.lead_tools import (
    classify_user_intent,
    clear_strategy,
    create_workbench_gene_set,
    delete_step,
    export_gene_set,
    get_live_strategy_state,
    list_workbench_gene_sets,
    read_gene_record,
    read_ledger_section,
    remember,
    run_gene_set_enrichment,
)
from pathfinder.ai.lead.sub_agent_dispatch import (
    build_strategy,
    recover_failed_steps,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import (
    LeadResponse,
    hold_the_turn_contract,
)
from pathfinder.ai.lead.verify_dispatch import verify_strategy
from pathfinder.ai.tools.standalone.control_sets import (
    build_control_set,
    import_control_ids_from_gene_set,
    import_control_ids_from_strategy,
    list_control_sets,
)
from pathfinder.ai.tools.standalone.scored_comparison import compare_variants_scored
from pathfinder.ai.tools.standalone.variant_comparison import compare_search_variants
from pathfinder.ai.tools.toolsets import eda
from pathfinder.platform.refusals import agent_capabilities


def turn_tool_sources(ctx: RunContext[LeadDeps]) -> AbstractToolset[Any] | None:
    """The servers this turn resolved, as the tools of this run."""
    return one_toolset(ctx.deps.runtime.tool_sources)


LeadAgent = Agent[LeadDeps, LeadResponse | DeferredToolRequests]


LEAD_MODEL = "openai:gpt-5.6-luna"


def build_lead_agent() -> LeadAgent:
    """A Lead agent for one turn.

    Each turn gets its own instance, so a per-turn model override never
    reaches another turn.
    """
    agent: LeadAgent = Agent(
        LEAD_MODEL,
        output_type=[LeadResponse, DeferredToolRequests],
        deps_type=LeadDeps,
        instructions=LEAD_INSTRUCTIONS,
        tools=[
            Tool(classify_user_intent),
            Tool(remember),
            Tool(create_workbench_gene_set),
            Tool(list_workbench_gene_sets),
            Tool(run_gene_set_enrichment, sequential=True, max_retries=3),
            Tool(export_gene_set),
            Tool(read_ledger_section),
            Tool(read_gene_record),
            Tool(get_live_strategy_state),
            Tool(frame_problem),
            Tool(edit_strategy),
            Tool(build_strategy),
            Tool(recover_failed_steps),
            Tool(verify_strategy),
            Tool(compare_search_variants),
            Tool(build_control_set),
            Tool(list_control_sets),
            Tool(import_control_ids_from_gene_set),
            Tool(import_control_ids_from_strategy),
            Tool(compare_variants_scored),
            Tool(clear_strategy, requires_approval=True),
            Tool(delete_step, requires_approval=True),
            Tool(consult_user, requires_approval=True),
        ],
        toolsets=[eda.build_toolset(), turn_tool_sources],
        capabilities=agent_capabilities(
            [
                Thinking(effort="medium"),
                PrepareTools[LeadDeps](apply_tool_preconditions),
                *(ProcessHistory[LeadDeps](p) for p in HISTORY_PROCESSORS),
            ],
        ),
        retries=3,
        description="The user's voice - orchestrates sub-agents via the Ledger",
        name="lead",
        defer_model_check=True,
    )
    for fn in (
        pinned_user_memories,
        pinned_user_prompt,
        pinned_user_intent,
        pinned_operational_spec,
        pinned_eda_sheet,
        pinned_ledger_summary,
        pinned_run_budget,
    ):
        agent.instructions(fn)
    agent.instructions(machine_guarantees_pin(agent.toolsets))
    agent.instructions(pinned_turn_briefing)
    agent.output_validator(hold_the_turn_contract)
    return agent
