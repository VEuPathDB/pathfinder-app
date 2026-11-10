from __future__ import annotations

from typing import Final

from assistant_core.conversation.history import HISTORY_PROCESSORS
from pydantic_ai import Agent, DeferredToolRequests, RunContext, Tool
from pydantic_ai.capabilities import PrepareTools, ProcessHistory
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import AbstractToolset, FunctionToolset

from pathfinder.ai.agents._instructions import pinned_run_budget, pinned_user_memories
from pathfinder.ai.agents.tool_vocabulary import READ_ONLY_TOOLS
from pathfinder.ai.capabilities.site_reads import SiteReadFailures
from pathfinder.ai.explore._explore_instructions import (
    EXPLORE_INSTRUCTIONS,
    EXPLORE_OFF_TOPIC_REDIRECT,
)
from pathfinder.ai.explore.account_reads import (
    ask_to_read_the_account,
    list_my_threads,
    read_gene_set,
    read_my_strategies,
    read_my_thread,
)
from pathfinder.ai.explore.explore_tools import catalog_reads, propose_readings
from pathfinder.ai.explore.readings_card import (
    READINGS_CARD_DESCRIPTION,
    readings_card_can_ask,
)
from pathfinder.ai.lead.intent_gate import turn_is_off_topic
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
from pathfinder.ai.lead.linked_pages import pinned_linked_pages
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.gene_record import (
    offered_where_genes_are_held,
    read_gene_record,
)
from pathfinder.ai.tools.standalone.record_reads import (
    list_record_columns,
    read_search_table,
)
from pathfinder.ai.tools.toolsets import eda
from pathfinder.ai.tools.toolsets._refusals import RefusalMemoryToolset
from pathfinder.platform.model_catalog import EXPLORE_MODELS
from pathfinder.platform.refusals import agent_capabilities

ExploreAgent = Agent[LeadDeps, str | DeferredToolRequests]

EXPLORE_MODEL: Final = EXPLORE_MODELS["openai"]["default"]


def build_explore_toolset() -> AbstractToolset[LeadDeps]:
    base: FunctionToolset[LeadDeps] = FunctionToolset(
        tools=[
            Tool(propose_readings),
            Tool(
                consult_user,
                requires_approval=True,
                args_validator=readings_card_can_ask,
                description=READINGS_CARD_DESCRIPTION,
            ),
            *catalog_reads(),
            Tool(list_record_columns),
            Tool(read_search_table),
            Tool(read_gene_record, prepare=offered_where_genes_are_held),
            Tool(get_live_strategy_state),
            Tool(list_gene_sets),
            Tool(ask_to_read_the_account, requires_approval=True),
            Tool(read_my_strategies),
            Tool(list_my_threads),
            Tool(read_my_thread),
            Tool(read_gene_set),
            Tool(search_memory),
            Tool(remember),
        ],
    )
    return RefusalMemoryToolset(wrapped=base, reads=READ_ONLY_TOOLS)


_SHARED_TOOLS: Final = frozenset(
    {
        "search_eda_studies",
        "describe_eda_study",
        "open_eda_analysis",
        "set_eda_filters",
        "preview_eda_subset",
        "run_eda_compute",
        "run_eda_dimensionality_reduction",
        "read_eda_statistics",
        "optimize_search_parameters",
    }
)


def _explore_may_call(ctx: RunContext[LeadDeps], tool_def: ToolDefinition) -> bool:
    del ctx
    return tool_def.name in _SHARED_TOOLS


def pinned_off_topic_redirect(ctx: RunContext[LeadDeps]) -> str | None:
    return EXPLORE_OFF_TOPIC_REDIRECT if turn_is_off_topic(ctx.deps) else None


async def _no_tool_off_topic(
    ctx: RunContext[LeadDeps], tool_defs: list[ToolDefinition]
) -> list[ToolDefinition]:
    return [] if turn_is_off_topic(ctx.deps) else tool_defs


def build_explore_agent() -> ExploreAgent:
    agent: ExploreAgent = Agent(
        EXPLORE_MODEL,
        output_type=[str, DeferredToolRequests],
        deps_type=LeadDeps,
        instructions=EXPLORE_INSTRUCTIONS,
        toolsets=[
            build_explore_toolset(),
            eda.build_toolset().filtered(_explore_may_call),
            build_sweep_toolset().filtered(_explore_may_call),
            turn_tool_sources,
        ],
        capabilities=agent_capabilities(
            [
                SiteReadFailures[LeadDeps](reads=READ_ONLY_TOOLS),
                PrepareTools[LeadDeps](_no_tool_off_topic),
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
        pinned_linked_pages,
        pinned_run_budget,
        pinned_off_topic_redirect,
    ):
        agent.instructions(fn)
    return agent
