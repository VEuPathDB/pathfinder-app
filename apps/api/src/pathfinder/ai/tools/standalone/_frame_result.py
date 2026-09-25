"""The criterion a set_criterion call answers with, and its one-line summary."""

from __future__ import annotations

from assistant_core.graph.stream_events import ToolSummaryStatus
from assistant_core.graph.tool_summary import count_noun, with_summary
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.wdk import WDKSearch

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._catalog_models import (
    search_display_name,
    what_it_finds,
)
from pathfinder.ai.tools.standalone._frame_count import criterion_line
from pathfinder.domain.strategy.operational_spec import (
    OpenSlot,
    ParameterAlternatives,
)
from pathfinder.domain.strategy.step_rationale import SearchRationale
from pathfinder.services.strategies.saved_library import SavedStrategyListing


class SetCriterionResult(CamelModel):
    """Result of binding a criterion to a WDK search and resolving its params."""

    criterion_id: str
    search_name: str
    # The search's name on the site, and its one-line summary once bound: what
    # the step runs, which is what the reply names.
    what_runs: str = ""
    # The saved strategy this criterion reuses as its input, when it names one.
    saved_strategy: SavedStrategyListing | None = None
    # Every visible parameter name mapped to null, in sheet order.
    params_template: dict[str, None] = Field(default_factory=dict)
    # True when this call opened the parameter sheet. Nothing is recorded then:
    # the sheet is pinned in the instructions and the next call decides it.
    sheet_pinned: bool = False
    # Each bound parameter with its value, so a wrong value is visible where a
    # bare name would hide it.
    resolved_params: dict[str, str] = Field(default_factory=dict)
    # Params the search defaulted. State these to the user with their values.
    defaulted_params: list[str] = Field(default_factory=list)
    open_slots: list[OpenSlot] = Field(default_factory=list)
    # The records this binding matches, or null when no count was read.
    result_count: int | None = None
    # Filled only when the binding matches no record: one entry per vocabulary
    # parameter that holds values this binding did not take.
    alternatives: list[ParameterAlternatives] = Field(default_factory=list)
    # Dependent params whose vocabulary changed once the parents were bound.
    # A non-empty list means nothing was recorded; decide these and re-call.
    # The fresh vocabulary is on the pinned sheet.
    redecide: list[str] = Field(default_factory=list)
    # Why the criterion runs this search, against what the catalog answered.
    rationale: SearchRationale | None = None
    # Searches of this pass the site could not answer, so no word of the
    # criterion was compared against them. Absent when every one was read.
    unread_searches: list[str] = Field(
        default_factory=list, exclude_if=lambda names: not names
    )


def criterion_return(
    ctx: RunContext[AgentDeps],
    result: SetCriterionResult,
    record_type: str,
    definition: WDKSearch,
) -> ToolReturn[SetCriterionResult]:
    """The bound criterion, or the parameters the call still leaves open.

    The sheet's own heading carries the summary, so the sheet-opening return
    stays short enough to survive history elision.
    """
    name = search_display_name(definition)
    runs = name if result.sheet_pinned else f"{name}: {what_it_finds(definition)}"
    result = result.model_copy(update={"what_runs": runs})
    line, status = _summary_line(result, record_type)
    if result.unread_searches:
        state = ctx.deps.agent_state
        shown = ", ".join(_shown(state, name) for name in result.unread_searches)
        line = f"{line}; not compared: {shown}"
    return with_summary(result, line, ctx=ctx, status=status)


def _shown(state: AgentToolState, search_name: str) -> str:
    """The name a catalog read of this pass showed the search by."""
    read = state.last_read_answering(search_name)
    hit = None if read is None else read.hit(search_name)
    return hit.display_name if hit is not None and hit.display_name else search_name


def _summary_line(
    result: SetCriterionResult, record_type: str
) -> tuple[str, ToolSummaryStatus]:
    """The line the call's result writes, before the searches it left out."""
    if result.sheet_pinned:
        return (
            f"{result.criterion_id}: sheet pinned, "
            f"{count_noun(len(result.params_template), 'parameter')} to decide"
        ), "warn"
    pending = len(result.redecide) + len(result.open_slots)
    if pending:
        return (
            f"{result.criterion_id}: {count_noun(pending, 'parameter')} still open"
        ), "warn"
    line, status = criterion_line(
        result.criterion_id,
        result.search_name,
        record_type,
        result.result_count,
        result.alternatives,
    )
    if result.rationale is not None:
        line = f"{line}, {result.rationale.short}"
    return line, status
