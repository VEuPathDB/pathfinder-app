from __future__ import annotations

from assistant_core.graph.tool_summary import count_noun, with_summary
from pydantic_ai import ModelRetry, RunContext, ToolFailed
from pydantic_ai.messages import ToolReturn
from veupathdb.wdk import get_site
from veupathdb_mcp.wdk import IdListDataset, IdListStepCountError, counted_id_list

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.intent import REQUEST_INTENTS
from pathfinder.ai.tools.standalone._frame_eda import refuse_a_waiting_criterion
from pathfinder.ai.tools.standalone._frame_result import (
    ComputedGroupsBinding,
    SetCriterionResult,
)
from pathfinder.ai.tools.standalone._frame_roles import (
    refuse_a_transform_on_a_saved_input,
)
from pathfinder.domain.strategy.computed_groups import HeldComparison
from pathfinder.domain.strategy.operational_spec import BoundValue, Criterion

GROUPS_DISPLAY_NAME = "Groups"


def _held(ctx: RunContext[AgentDeps], handle: str) -> HeldComparison:
    held = ctx.deps.agent_state.computed_comparisons.get(handle.strip())
    if held is None:
        msg = (
            f"computed_groups names {handle}, and no computed comparison of this "
            "turn is held under that handle. Call build_phyletic_expression and "
            "pass the handle of its computed answer; nothing was recorded."
        )
        raise ModelRetry(msg)
    if held.answer.groups == 0:
        msg = (
            f"The computed comparison {held.handle} selects no group, so there is "
            "no list to save; nothing was recorded."
        )
        raise ModelRetry(msg)
    return held


def _refuse_an_unasked_save(ctx: RunContext[AgentDeps], handle: str) -> None:
    deps = ctx.deps
    if deps.intent in REQUEST_INTENTS or handle in deps.turn_markers.saves_asked:
        return
    msg = (
        f"Saving {handle} uploads its groups to the researcher's account, and this "
        "turn neither asks for a strategy nor answers a card that offered the save. "
        "Answer from the counts; the card offers the save. Nothing was recorded."
    )
    raise ModelRetry(msg)


async def _saved_list(site_id: str, held: HeldComparison, name: str) -> IdListDataset:
    try:
        return await counted_id_list(
            site_id,
            list(held.answer.group_ids),
            record_type="group",
            strategy_name=name,
        )
    except IdListStepCountError as exc:
        msg = (
            f"set_criterion cannot hold the computed groups as a list step: "
            f"{exc.detail} Nothing was recorded and no step was saved. The counted "
            "answer stands: state its counts, and do not build the comparison "
            "again to save it."
        )
        raise ToolFailed(msg) from exc


async def set_computed_criterion(
    ctx: RunContext[AgentDeps], stated: Criterion, *, handle: str
) -> ToolReturn[SetCriterionResult]:
    state = ctx.deps.agent_state
    refuse_a_waiting_criterion(state, stated.id)
    refuse_a_transform_on_a_saved_input(stated.id, stated.role, "computed comparison")
    held = _held(ctx, handle)
    _refuse_an_unasked_save(ctx, held.handle)
    site_id = ctx.deps.site_id
    name = held.step_name(stated.text)
    description = held.description(get_site(site_id).name)
    saved = await _saved_list(site_id, held, name)
    state.frame_set_criterion(
        stated.model_copy(
            update={
                "search_name": saved.search_name,
                "record_class": saved.record_type,
                "search_display_name": name,
                "param_display_names": {saved.param_name: GROUPS_DISPLAY_NAME},
                "resolved_params": {
                    param: BoundValue(
                        value=value,
                        source="chosen",
                        basis=description,
                        label=held.label(),
                    )
                    for param, value in saved.params().items()
                },
                "result_count": held.answer.groups,
            }
        )
    )
    state.computed_comparisons[held.handle] = held.model_copy(
        update={"dataset_id": str(saved.dataset_id)}
    )
    binding = ComputedGroupsBinding(
        handle=held.handle,
        groups=held.answer.groups,
        step_name=name,
        description=description,
    )
    return with_summary(
        SetCriterionResult(
            criterion_id=stated.id,
            search_name=saved.search_name,
            result_count=held.answer.groups,
            computed_groups=binding,
        ),
        f"{stated.id} holds the {count_noun(binding.groups, 'computed group')}, "
        "saved as a list",
        ctx=ctx,
    )
