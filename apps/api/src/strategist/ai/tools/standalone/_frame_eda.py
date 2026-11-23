"""The refusals a search definition passes before a criterion binds to it, and
the analysis criteria FRAME keeps as the EDA tools bound them."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue
from pydantic_ai import RunContext, ToolReturn
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import (
    EDA_DATASET_ID_PARAM,
    EdaBackedSearch,
    format_param_info_typed,
)

from strategist.ai.agents.state import AgentToolState
from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.tools.standalone._frame_answers import answers_the_sheet_lacks
from strategist.ai.tools.standalone._frame_result import (
    SetCriterionResult,
    criterion_return,
    wait_instruction,
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
    raise ProblemsRefusal(
        Problems.one(RefusalKey(check="bound_analysis", criterion=criterion_id), msg)
    )


def waiting_problems(state: AgentToolState, criterion_id: str) -> Problems:
    """A criterion waiting for its analysis is bound by the export and nothing else.

    An EDA-backed search restates it as waiting, so only another binding
    reaches this problem.
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
        return Problems()
    return Problems.one(
        RefusalKey(check="waiting"),
        f"{criterion_id} waits for the analysis workflow on dataset {waiting}, and "
        f'create_eda_step(criterion_id="{criterion_id}") binds it and nothing '
        f"else does. Keep it in the structure where it stands and bind no other "
        f"search for it.",
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
                f"and {search_name} can only wait for the analysis workflow; "
                f"{criterion_id} stays as it is. Name a new "
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
            f"analysis workflow opened. Name a new criterion "
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
    if dataset is None:
        found.append(
            f"{search_name} is EDA-backed and names no dataset, so "
            f"{criterion.id} cannot wait for its analysis yet. Re-call "
            f'set_criterion with params={{"{EDA_DATASET_ID_PARAM}": "<dataset '
            f'id>"}} and nothing else, naming the dataset the comparison runs on.'
        )
    key = RefusalKey(check="eda_wait", criterion=criterion.id, search=search_name)
    waits = Problems(found=tuple(Problem(key=key, sentence=s) for s in found))
    lacked = answers_the_sheet_lacks(criterion.answers, sheet)
    return waits.plus(lacked.under(criterion=criterion.id, search=search_name))


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
    *,
    early: Problems,
) -> ToolReturn[SetCriterionResult]:
    state = ctx.deps.agent_state
    dataset = _named_dataset(params) or described.default_dataset_id
    problems = early.under(criterion=stated.id, search=described.search_name).plus(
        eda_wait_problems(state, definition, stated, dataset)
    )
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
