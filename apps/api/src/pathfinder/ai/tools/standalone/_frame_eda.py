"""The refusals a search definition passes before a criterion binds to it, and
the analysis criteria FRAME keeps as the EDA tools bound them."""

from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import (
    EDA_ANALYSIS_SPEC_PARAM,
    EDA_DATASET_ID_PARAM,
    eda_backed_search,
)

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._frame_proposals import ParamProposals
from pathfinder.ai.tools.standalone._frame_roles import (
    refuse_a_role_the_search_cannot_take,
)
from pathfinder.domain.strategy.operational_spec import Criterion


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
        f"Keep it as it is and state it kept; do not re-bind it, and do not "
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
    params: ParamProposals | None,
) -> None:
    """Every refusal a search passes before a criterion binds to it.

    ``criterion`` is what the call states, and ``params`` what it proposes.
    """
    _refuse_an_eda_backed_search(
        ctx.deps.agent_state, definition, criterion, _named_dataset(params)
    )
    refuse_a_waiting_criterion(ctx.deps.agent_state, criterion.id)
    await refuse_a_role_the_search_cannot_take(
        ctx, record_type, definition, criterion.role
    )


def _named_dataset(params: ParamProposals | None) -> str | None:
    """The dataset a proposal names for an EDA-backed search, if it names one."""
    match None if params is None else params.get(EDA_DATASET_ID_PARAM):
        case str() as dataset if dataset:
            return dataset
        case _:
            return None


def _refuse_what_the_id_holds(
    state: AgentToolState, criterion_id: str, search_name: str, dataset: str
) -> None:
    """The waiting record goes only where it replaces nothing the draft holds.

    A bound criterion keeps its search, and a waiting criterion keeps the
    dataset its analysis workflow opened.
    """
    held = next(
        (c for c in state.operational_spec_draft.criteria if c.id == criterion_id),
        None,
    )
    if held is not None and held.bound:
        msg = (
            f"{criterion_id} is bound to {held.search_name or 'a saved strategy'}, "
            f"and {search_name} can only wait for the analysis workflow; nothing "
            f"was recorded and {criterion_id} stays as it is. Name a new criterion "
            f"id for the comparison on {dataset}."
        )
        raise ModelRetry(msg)
    waited_on = None if held is None else held.needs_analysis_on
    if waited_on is None or waited_on == dataset:
        return
    msg = (
        f"{criterion_id} waits on dataset {waited_on}, and {search_name} runs on "
        f"dataset {dataset}. The waiting criterion keeps the dataset the "
        f"analysis workflow opened; nothing was recorded. Name a new criterion "
        f"id for a comparison on {dataset}."
    )
    raise ModelRetry(msg)


def _refuse_an_eda_backed_search(
    state: AgentToolState,
    definition: WDKSearch,
    criterion: Criterion,
    named_dataset: str | None,
) -> None:
    """A criterion never binds to a search whose subset is an EDA analysis: it
    waits for the analysis workflow on the dataset the call names, else on the
    one the search starts with."""
    described = eda_backed_search(definition)
    if described is None:
        return
    dataset = named_dataset or described.default_dataset_id
    if dataset is None:
        msg = (
            f"{described.search_name} is EDA-backed and names no dataset, so "
            f"{criterion.id} cannot wait for its analysis yet. Re-call "
            f'set_criterion with params={{"{EDA_DATASET_ID_PARAM}": "<dataset '
            f'id>"}} and nothing else, naming the dataset the comparison runs on.'
        )
        raise ModelRetry(msg)
    _refuse_what_the_id_holds(state, criterion.id, described.search_name, dataset)
    state.frame_set_criterion(
        Criterion(
            id=criterion.id,
            text=criterion.text,
            role=criterion.role,
            needs_analysis_on=dataset,
        )
    )
    msg = (
        f"{described.search_name} is EDA-backed: its {EDA_ANALYSIS_SPEC_PARAM} "
        f"is an analysis document only the Lead's EDA tools produce, so no value "
        f"here realizes {criterion.id}. It is recorded as needing the analysis "
        f"workflow on dataset {dataset}. Put {criterion.id} in the structure where "
        f"the request puts it, bind no other search for it, do not call "
        f"drop_criterion for it, and return spec_ready once the rest is bound."
    )
    raise ModelRetry(msg)
