"""The refusals a search definition passes before a criterion binds to it, and
the analysis criteria FRAME keeps as the EDA tools bound them."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue
from pydantic_ai import ModelRetry, RunContext, ToolReturn
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import (
    EDA_DATASET_ID_PARAM,
    EdaBackedSearch,
    format_param_info_typed,
)

from strategist.ai.agents.state import AgentToolState
from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.tools.standalone._frame_answers import params_the_sheet_lacks
from strategist.ai.tools.standalone._frame_result import (
    SetCriterionResult,
    criterion_return,
    wait_instruction,
)
from strategist.ai.tools.standalone._frame_roles import (
    refuse_a_role_the_search_cannot_take,
)
from strategist.domain.refusal import Problem, Problems, RefusalKey
from strategist.domain.strategy.operational_spec import Criterion
from strategist.platform.refusals import ProblemsRefusal


def refuse_a_bound_analysis(state: AgentToolState, criterion_id: str) -> None:
    """A criterion the EDA tools bound is that analysis, so FRAME keeps it."""
    words = next(
        (
            c.analysis.words
            for c in state.operational_spec_draft.criteria
            if c.id == criterion_id and c.analysis is not None
        ),
        None,
    )
    if words is None:
        return
    msg = (
        f"{criterion_id} is bound to the analysis workflow ({words}). "
        f"Keep it as it is; do not re-bind it, and do not "
        f"restate its comparison with another search. Only the Lead removes it, "
        f"with delete_step."
    )
    raise ModelRetry(msg)


def refuse_a_waiting_criterion(state: AgentToolState, criterion_id: str) -> None:
    """A criterion waiting for its analysis is bound by the export and nothing else.

    An EDA-backed search restates it as waiting, so only another binding
    reaches this refusal.
    """
    waiting = next(
        (
            c.needs_analysis_on
            for c in state.operational_spec_draft.criteria
            if c.id == criterion_id and c.pending_analysis
        ),
        None,
    )
    if waiting is None:
        return
    msg = (
        f"{criterion_id} waits for the analysis workflow on dataset {waiting}, and "
        f'create_eda_step(criterion_id="{criterion_id}") binds it and nothing '
        f"else does. Keep it in the structure where it stands and bind no other "
        f"search for it; nothing was recorded."
    )
    raise ModelRetry(msg)


async def refuse_a_search_the_criterion_cannot_use(
    ctx: RunContext[AgentDeps],
    record_type: str,
    definition: WDKSearch,
    criterion: Criterion,
) -> None:
    """Every refusal a search passes before a criterion binds to it."""
    refuse_a_waiting_criterion(ctx.deps.agent_state, criterion.id)
    await refuse_a_role_the_search_cannot_take(
        ctx, record_type, definition, criterion.role
    )


def _named_dataset(params: Mapping[str, JsonValue] | None) -> str | None:
    """The dataset a proposal names for an EDA-backed search, if it names one."""
    match None if params is None else params.get(EDA_DATASET_ID_PARAM):
        case str() as dataset if dataset:
            return dataset
        case _:
            return None


def _held_problems(
    state: AgentToolState, criterion_id: str, search_name: str, dataset: str | None
) -> list[str]:
    held = next(
        (c for c in state.operational_spec_draft.criteria if c.id == criterion_id),
        None,
    )
    if held is None:
        return []
    if held.bound:
        on = f" for the comparison on {dataset}" if dataset else ""
        return [
            (
                f"{criterion_id} is bound to {held.search_name or 'a saved strategy'}, "
                f"and {search_name} can only wait for the analysis workflow; nothing "
                f"was recorded and {criterion_id} stays as it is. Name a new "
                f"criterion id{on}."
            )
        ]
    waited_on = held.needs_analysis_on
    if dataset is None or waited_on is None or waited_on == dataset:
        return []
    return [
        (
            f"{criterion_id} waits on dataset {waited_on}, and {search_name} runs on "
            f"dataset {dataset}. The waiting criterion keeps the dataset the "
            f"analysis workflow opened; nothing was recorded. Name a new criterion "
            f"id for a comparison on {dataset}."
        )
    ]


def eda_wait_problems(
    state: AgentToolState,
    definition: WDKSearch,
    criterion: Criterion,
    dataset: str | None,
) -> Problems:
    search_name = definition.url_segment
    found = _held_problems(state, criterion.id, search_name, dataset)
    sheet = format_param_info_typed(definition.parameters or [], organism=None)
    lacked = params_the_sheet_lacks(criterion.answers, sheet)
    if lacked is not None:
        found.append(lacked)
    if dataset is None:
        found.append(
            f"{search_name} is EDA-backed and names no dataset, so "
            f"{criterion.id} cannot wait for its analysis yet. Re-call "
            f'set_criterion with params={{"{EDA_DATASET_ID_PARAM}": "<dataset '
            f'id>"}} and nothing else, naming the dataset the comparison runs on.'
        )
    key = RefusalKey(check="eda_wait", criterion=criterion.id, search=search_name)
    return Problems(found=tuple(Problem(key=key, sentence=s) for s in found))


def record_the_wait(state: AgentToolState, criterion: Criterion, dataset: str) -> None:
    state.frame_set_criterion(
        Criterion(
            id=criterion.id,
            text=criterion.text,
            role=criterion.role,
            answers=criterion.answers,
            needs_analysis_on=dataset,
        )
    )


def wait_for_the_analysis(
    ctx: RunContext[AgentDeps],
    stated: Criterion,
    described: EdaBackedSearch,
    definition: WDKSearch,
    record_type: str,
    params: Mapping[str, JsonValue] | None,
) -> ToolReturn[SetCriterionResult]:
    state = ctx.deps.agent_state
    dataset = _named_dataset(params) or described.default_dataset_id
    problems = eda_wait_problems(state, definition, stated, dataset)
    if dataset is None or not problems.empty:
        raise ProblemsRefusal(problems)
    record_the_wait(state, stated, dataset)
    return criterion_return(
        ctx,
        SetCriterionResult(
            criterion_id=stated.id,
            search_name=described.search_name,
            waits_for_analysis_on=dataset,
            next_step=wait_instruction(described.search_name, stated.id, dataset),
        ),
        record_type,
        definition,
    )
