"""FRAME-phase toolset - retrieval-grounded operationalize + bind + resolve."""

from pydantic_ai.tools import RunContext
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.catalog import (
    browse_search_categories,
    get_record_types,
    list_searches,
    list_transforms,
    lookup_phyletic_codes,
    search_example_plans,
    search_for_searches,
)
from pathfinder.ai.tools.standalone.catalog_discovery import (
    get_parameter_options,
    get_search_overview,
)
from pathfinder.ai.tools.standalone.frame_spec import (
    drop_criterion,
    set_criterion,
)
from pathfinder.ai.tools.standalone.frame_structure import set_structure
from pathfinder.ai.tools.standalone.gene import (
    get_ai_expression_summary,
    lookup_gene_records,
)
from pathfinder.ai.tools.standalone.memory_tools import remember, search_memory
from pathfinder.ai.tools.standalone.saved_strategies import list_saved_strategies
from pathfinder.ai.tools.standalone.strategy_graph import get_strategy
from pathfinder.ai.tools.standalone.think import think
from pathfinder.ai.tools.toolsets._dynamic import (
    EnumOverrides,
    ValidatingEnumToolset,
)


def _frame_enum_overrides(ctx: RunContext[AgentDeps]) -> EnumOverrides:
    state = ctx.deps.agent_state
    known = set(state.candidate_search_names()) | set(state.discovered_search_names())
    # Withdraw searches already given up on this turn so the model cannot keep
    # re-selecting something VEuPathDB is 500ing on. If that would leave nothing
    # to choose from, keep the full set: an empty enum invalidates every call and
    # removes the model's ability to route around the outage at all.
    reachable = known - ctx.deps.service_outage.unavailable_searches()
    candidates = sorted(reachable or known)
    overrides: EnumOverrides = {}
    if reachable:
        overrides[("get_search_overview", "search_name")] = candidates
        overrides[("set_criterion", "search_name")] = candidates
        overrides[("get_parameter_options", "search_name")] = candidates
    return overrides


def build_toolset() -> AbstractToolset[AgentDeps]:
    """FRAME toolset: retrieve candidate searches and the user's saved strategies,
    read a search's parameter sheet, bind criteria with the params proposed from that
    sheet, assemble the structure. ``set_criterion`` is enum-guarded to real candidate
    searches so the model cannot invent names."""
    base: FunctionToolset[AgentDeps] = FunctionToolset(
        max_retries=3,
        tools=[
            get_record_types,
            search_for_searches,
            browse_search_categories,
            list_searches,
            list_transforms,
            search_example_plans,
            get_search_overview,
            get_parameter_options,
            lookup_phyletic_codes,
            list_saved_strategies,
            set_criterion,
            set_structure,
            drop_criterion,
            lookup_gene_records,
            get_ai_expression_summary,
            get_strategy,
            think,
            search_memory,
            remember,
        ],
    )
    return ValidatingEnumToolset(wrapped=base, build_overrides=_frame_enum_overrides)
