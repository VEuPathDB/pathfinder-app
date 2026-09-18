"""Verification-phase toolset for testing, analyzing, and exporting results."""

from pydantic_ai.tools import RunContext, Tool, ToolDefinition
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.escape_hatch import (
    request_search_inspection,
)
from pathfinder.ai.tools.standalone.execution import get_estimated_size
from pathfinder.ai.tools.standalone.experiment import (
    run_control_tests_on_search,
    run_control_tests_on_step,
)
from pathfinder.ai.tools.standalone.export import export_gene_set
from pathfinder.ai.tools.standalone.gene import (
    get_ai_expression_summary,
    lookup_gene_records,
    resolve_gene_ids_to_records,
)
from pathfinder.ai.tools.standalone.memory_tools import remember, search_memory
from pathfinder.ai.tools.standalone.results import (
    get_download_url,
    get_sample_records,
)
from pathfinder.ai.tools.standalone.strategy_graph import (
    check_study_step,
    get_strategy,
)
from pathfinder.ai.tools.standalone.think import think
from pathfinder.ai.tools.standalone.workbench import (
    create_workbench_gene_set,
    list_workbench_gene_sets,
    run_gene_set_enrichment,
)
from pathfinder.ai.tools.standalone.workbench_read import (
    get_confidence_scores,
    get_enrichment_results,
    get_evaluation_summary,
    get_experiment_config,
    get_result_gene_lists,
)
from pathfinder.ai.tools.toolsets._dynamic import (
    DynamicEnumToolset,
    EnumOverrides,
    live_wdk_step_ids,
)


def _verification_enum_overrides(
    ctx: RunContext[AgentDeps],
) -> EnumOverrides:
    """Constrain ``wdk_step_id`` args to the steps that exist in WDK.

    A ``wdk_step_id`` is assigned when a step is pushed, so only pushed steps
    can be queried and the enum holds the ids in
    ``strategy_session.sync_state.wdk_step_ids``.
    """
    overrides: EnumOverrides = {}
    wdk_ids = live_wdk_step_ids(ctx.deps.strategy_session)
    if wdk_ids:
        for tool in (
            "get_estimated_size",
            "get_sample_records",
            "get_download_url",
            "run_control_tests_on_step",
        ):
            overrides[(tool, "wdk_step_id")] = list(wdk_ids)
    return overrides


ENRICHMENT_TOOL = "run_gene_set_enrichment"


def _warranted_by_the_delta(
    ctx: RunContext[AgentDeps],
    tool_def: ToolDefinition,
) -> bool:
    """Offer enrichment only on a turn whose delta earns its cost."""
    if tool_def.name != ENRICHMENT_TOOL:
        return True
    return ctx.deps.verification_scope.warrants_enrichment()


def build_toolset() -> AbstractToolset[AgentDeps]:
    """Build the verification-phase toolset.

    Phase exit is handled by ``output_type=VerificationDecision`` on the
    verification agent - no ``finish_*`` tool is exposed.

    Every ``@durable_tool`` is also registered with ``sequential=True``.
    A durable call ends the run deferred, and one parked call is checkpointed
    per turn, so a batch that fires two of them would leave the second
    unanswered.

    ``run_gene_set_enrichment`` is offered only when the turn's delta warrants
    it, so an edit of one step is verified by its counts.
    """
    base: FunctionToolset[AgentDeps] = FunctionToolset(
        max_retries=3,
        tools=[
            get_estimated_size,
            get_sample_records,
            get_download_url,
            Tool(run_control_tests_on_step, sequential=True, max_retries=3),
            run_control_tests_on_search,
            lookup_gene_records,
            get_ai_expression_summary,
            resolve_gene_ids_to_records,
            create_workbench_gene_set,
            Tool(run_gene_set_enrichment, sequential=True, max_retries=3),
            list_workbench_gene_sets,
            export_gene_set,
            get_evaluation_summary,
            get_enrichment_results,
            get_confidence_scores,
            get_experiment_config,
            get_result_gene_lists,
            get_strategy,
            check_study_step,
            request_search_inspection,
            think,
            search_memory,
            remember,
        ],
    )
    return DynamicEnumToolset(
        wrapped=base,
        build_overrides=_verification_enum_overrides,
    ).filtered(_warranted_by_the_delta)
