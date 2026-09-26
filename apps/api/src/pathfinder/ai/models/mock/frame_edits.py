"""The FRAME scripts of the arcs that change a strategy: on an EDIT work order
they edit the tree it prints, and on a fresh thread they bind the whole spec."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from assistant_core.models.scripted import current_scope_id
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.edit_frame import (
    grown_call,
    param_edit_call,
    removed_step_call,
    replaced_step_call,
    workspace_criteria,
)
from pathfinder.ai.models.mock.frame_arcs import on_edit_order
from pathfinder.ai.models.mock.growths import (
    Growth,
    added_growth,
    orthologs_growth,
    orthologs_spec,
    round_trip_growth,
    round_trip_spec,
    syntenic_orthologs_spec,
)
from pathfinder.ai.models.mock.history import acted_tool_names
from pathfinder.ai.models.mock.reads import instructions_of
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.specs import criterion_replies
from pathfinder.ai.models.mock.strategy_specs import (
    EDITED_MIN_TM,
    RELAXED_MIN_TM,
    TM_DOMAINS,
    zero_spec,
)

Edit = Callable[[list[ModelMessage], str], ToolCallPart]


def _site() -> SiteValues:
    return SiteValues.for_site(current_scope_id.get())


def _param_edit(change: dict[str, str]) -> Edit:
    def edit(messages: list[ModelMessage], work_order: str) -> ToolCallPart:
        return param_edit_call(
            work_order,
            TM_DOMAINS,
            change,
            acted_tool_names(messages),
            criterion_replies(messages),
        )

    return edit


def _grow(
    messages: list[ModelMessage], work_order: str, growth: Growth
) -> ToolCallPart:
    return grown_call(
        work_order,
        growth,
        acted_tool_names(messages),
        criterion_replies(messages),
        instructions_of(messages),
    )


def _grown(growth: Callable[[SiteValues], Growth]) -> Edit:
    def edit(messages: list[ModelMessage], work_order: str) -> ToolCallPart:
        return _grow(messages, work_order, growth(_site()))

    return edit


def _added(messages: list[ModelMessage], work_order: str) -> ToolCallPart:
    held = {c.search_name for c in workspace_criteria(work_order)}
    return _grow(messages, work_order, added_growth(_site(), held))


def _replaced(messages: list[ModelMessage], work_order: str) -> ToolCallPart:
    held = {c.search_name for c in workspace_criteria(work_order)}
    (added,) = added_growth(_site(), held).criteria
    return replaced_step_call(
        work_order,
        TM_DOMAINS,
        added,
        acted_tool_names(messages),
        criterion_replies(messages),
        instructions_of(messages),
    )


def _removed(messages: list[ModelMessage], work_order: str) -> ToolCallPart:
    return removed_step_call(work_order, TM_DOMAINS, acted_tool_names(messages))


edit_param_frame = on_edit_order(_param_edit({"min_tm": EDITED_MIN_TM}))
relax_frame = on_edit_order(_param_edit({"min_tm": RELAXED_MIN_TM}), zero_spec)
add_step_frame = on_edit_order(_added)
replace_frame = on_edit_order(_replaced)
delete_frame = on_edit_order(_removed)
orthologs_frame = on_edit_order(
    _grown(partial(orthologs_growth, syntenic="no")), orthologs_spec
)
syntenic_frame = on_edit_order(
    _grown(partial(orthologs_growth, syntenic="yes")), syntenic_orthologs_spec
)
round_trip_frame = on_edit_order(_grown(round_trip_growth), round_trip_spec)
