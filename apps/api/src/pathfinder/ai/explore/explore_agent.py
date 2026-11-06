from __future__ import annotations

from typing import Final

from assistant_core.conversation.history import HISTORY_PROCESSORS
from pydantic_ai import Agent, DeferredToolRequests, RunContext, Tool
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import AbstractToolset, FunctionToolset

from pathfinder.ai.agents._instructions import pinned_run_budget, pinned_user_memories
from pathfinder.ai.agents.tool_vocabulary import READ_ONLY_TOOLS
from pathfinder.ai.capabilities.site_reads import SiteReadFailures
from pathfinder.ai.explore._explore_instructions import EXPLORE_INSTRUCTIONS
from pathfinder.ai.explore.explore_tools import catalog_reads, propose_readings
from pathfinder.ai.explore.readings_card import readings_card_can_ask
from pathfinder.ai.lead.lead_agent import build_sweep_toolset, turn_tool_sources
from pathfinder.ai.lead.lead_consult import consult_user
from pathfinder.ai.lead.lead_memory_tools import remember, search_memory
from pathfinder.ai.lead.lead_pins import (
    pinned_conversation,
    pinned_memory_index,
    pinned_user_prompt,
)
from pathfinder.ai.lead.lead_reads import get_live_strategy_state
from pathfinder.ai.lead.lead_tools import list_gene_sets
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.eda_step import create_eda_step
from pathfinder.ai.tools.standalone.gene_record import (
    offered_where_genes_are_held,
    read_gene_record,
)
from pathfinder.ai.tools.toolsets import eda
from pathfinder.ai.tools.toolsets._refusals import RefusalMemoryToolset
from pathfinder.platform.model_catalog import EXPLORE_MODELS
from pathfinder.platform.refusals import agent_capabilities

ExploreAgent = Agent[LeadDeps, str | DeferredToolRequests]

EXPLORE_MODEL: Final = EXPLORE_MODELS["openai"]


def build_explore_toolset() -> AbstractToolset[LeadDeps]:
    base: FunctionToolset[LeadDeps] = FunctionToolset(
        tools=[
            Tool(propose_readings),
            Tool(
                consult_user,
                requires_approval=True,
                args_validator=readings_card_can_ask,
            ),
            *catalog_reads(),
            Tool(read_gene_record, prepare=offered_where_genes_are_held),
            Tool(get_live_strategy_state),
            Tool(list_gene_sets),
            Tool(search_memory),
            Tool(remember),
        ],
    )
    return RefusalMemoryToolset(wrapped=base, reads=READ_ONLY_TOOLS)


def _writes_no_strategy(ctx: RunContext[LeadDeps], tool_def: ToolDefinition) -> bool:
    del ctx
    return tool_def.name != create_eda_step.__name__


def build_explore_agent() -> ExploreAgent:
    agent: ExploreAgent = Agent(
        EXPLORE_MODEL,
        output_type=[str, DeferredToolRequests],
        deps_type=LeadDeps,
        instructions=EXPLORE_INSTRUCTIONS,
        toolsets=[
            build_explore_toolset(),
            eda.build_toolset().filtered(_writes_no_strategy),
            build_sweep_toolset(),
            turn_tool_sources,
        ],
        capabilities=agent_capabilities(
            [
                SiteReadFailures[LeadDeps](reads=READ_ONLY_TOOLS),
                *(ProcessHistory[LeadDeps](p) for p in HISTORY_PROCESSORS),
            ],
        ),
        retries=3,
        name="explore",
        defer_model_check=True,
    )
    for fn in (
        pinned_user_memories,
        pinned_memory_index,
        pinned_conversation,
        pinned_user_prompt,
        pinned_run_budget,
    ):
        agent.instructions(fn)
    return agent
