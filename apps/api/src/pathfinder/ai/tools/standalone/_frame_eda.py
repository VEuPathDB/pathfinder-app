"""The refusals a search definition passes before a criterion binds to it."""

from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import EDA_ANALYSIS_SPEC_PARAM, eda_backed_search

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._frame_roles import (
    refuse_a_role_the_search_cannot_take,
)
from pathfinder.domain.strategy.operational_spec import (
    CriterionRole,
    DroppedCriterion,
)

EDA_DROP_REASON = (
    "EDA-backed criterion: the Lead builds it with open_eda_analysis, "
    "set_eda_filters, preview_eda_subset and create_eda_step."
)


async def refuse_a_search_the_criterion_cannot_use(
    ctx: RunContext[AgentDeps],
    record_type: str,
    definition: WDKSearch,
    role: CriterionRole,
    criterion_id: str,
    text: str,
) -> None:
    """Every refusal a search passes before a criterion binds to it."""
    _refuse_an_eda_backed_search(ctx.deps.agent_state, definition, criterion_id, text)
    await refuse_a_role_the_search_cannot_take(ctx, record_type, definition, role)


def _refuse_an_eda_backed_search(
    state: AgentToolState, definition: WDKSearch, criterion_id: str, text: str
) -> None:
    """A criterion never binds to a search whose subset is an EDA analysis.

    The analysis-spec parameter carries a whole analysis document, so no value
    a parameter sheet can propose realizes the criterion. The drop is recorded
    here, because the criterion never reaches the draft to be dropped later.
    """
    described = eda_backed_search(definition)
    if described is None:
        return
    dataset = described.default_dataset_id
    state.frame_record_drop(
        criterion_id,
        DroppedCriterion(text=text, reason=EDA_DROP_REASON, eda_dataset_id=dataset),
    )
    on_dataset = f", on dataset {dataset}" if dataset else ""
    msg = (
        f"{described.search_name} is EDA-backed: its {EDA_ANALYSIS_SPEC_PARAM} "
        f"is an analysis document only the Lead's EDA tools produce, so no "
        f"value here realizes {criterion_id}. It is recorded as dropped for "
        f"the Lead{on_dataset}. Do not call drop_criterion for it and do not "
        f"propose a value; carry on with the remaining criteria."
    )
    raise ModelRetry(msg)
