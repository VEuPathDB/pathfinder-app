from __future__ import annotations

from collections.abc import Mapping, Sequence

from assistant_core.graph.turn_state import UserQuestionAnswer
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.graph.state import PipelineState
from strategist.domain.unread import Unread
from strategist.services.strategies.sheet_params import (
    criterion_sheets,
    parameters_of_searches,
    read_sheets,
    unread_sheets,
)


async def card_sheets(
    state: PipelineState, answers: Sequence[UserQuestionAnswer]
) -> tuple[dict[str, list[ParameterInfo]], dict[str, Unread]]:
    """Every published parameter of each criterion a picked option binds a value
    on, the ones the site sets included, with each dependent vocabulary read
    under the values that criterion holds, by criterion id; and the sheet of
    each other such criterion, which the site did not answer."""
    spec = state.domain.operational_spec
    recorded = {q.question: q for q in state.domain.open_questions}
    bound = {
        values.criterion_id
        for answer in answers
        if (question := recorded.get(answer.prompt)) is not None
        for option in question.options
        if option.label in answer.chosen_labels
        and (values := option.values_bound()) is not None
    }
    criteria = [] if spec is None else [c for c in spec.criteria if c.id in bound]
    searches = {c.search_name for c in criteria if c.search_name}
    if not searches:
        return {}, {}
    reads = await parameters_of_searches(site_id=state.site_id, search_names=searches)
    unread = {
        c.id: failed
        for c in criteria
        if (failed := unread_sheets(reads).get(c.search_name)) is not None
    }
    under = await criterion_sheets(
        state.site_id, [c for c in criteria if c.id not in unread], read_sheets(reads)
    )
    return read_sheets(under), {**unread, **unread_sheets(under)}


def picks_on_unread_sheets(
    state: PipelineState,
    answers: Sequence[UserQuestionAnswer],
    unread: Mapping[str, Unread],
) -> dict[str, str]:
    recorded = {q.question: q for q in state.domain.open_questions}
    spec = state.domain.operational_spec
    searches = {} if spec is None else {c.id: c.search_name for c in spec.criteria}
    return {
        option.label: (
            f"the sheet of {searches[values.criterion_id]} was not read, so "
            f"{option.label!r} binds nothing: {unread[values.criterion_id].reason}"
        )
        for answer in answers
        if (question := recorded.get(answer.prompt)) is not None
        for option in question.options
        if option.label in answer.chosen_labels
        and (values := option.values_bound()) is not None
        and values.criterion_id in unread
    }
