"""The EDA toolset: explore a study in conversation and export a step."""

from pydantic_ai import Tool
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.eda_analysis import (
    open_eda_analysis,
    preview_eda_subset,
    set_eda_filters,
)
from pathfinder.ai.tools.standalone.eda_catalog import (
    describe_eda_study,
    search_eda_studies,
)
from pathfinder.ai.tools.standalone.eda_compute import (
    refuse_shared_labels,
    run_eda_compute,
)
from pathfinder.ai.tools.standalone.eda_step import create_eda_step


def build_toolset() -> AbstractToolset[LeadDeps]:
    """The seven EDA tools the Lead calls.

    ``run_eda_compute`` is registered sequential: one parked durable call is
    checkpointed per turn, so a batch that fires two of them would leave the
    second unanswered.
    """
    toolset: FunctionToolset[LeadDeps] = FunctionToolset(
        max_retries=3,
        tools=[
            search_eda_studies,
            describe_eda_study,
            open_eda_analysis,
            set_eda_filters,
            preview_eda_subset,
            Tool(
                run_eda_compute,
                sequential=True,
                max_retries=3,
                args_validator=refuse_shared_labels,
            ),
            create_eda_step,
        ],
    )
    return toolset
