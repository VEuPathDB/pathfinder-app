from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from http import HTTPStatus

from assistant_core.capabilities.repetition_guard import DEFAULT_REPETITION_THRESHOLD
from pydantic_ai import ModelRetry, RunContext
from veupathdb.errors import VEuPathDBError, WDKError

from pathfinder.ai.agents.unserved import SearchNotServedError, UnservedSearch
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.services.strategies.record_classes import search_record_types

_ANY_RECORD_TYPE = "any record type"


async def listed_record_type(
    ctx: RunContext[AgentDeps], criterion_id: str, search_name: str
) -> str:
    unserved = ctx.deps.agent_state.unserved_searches
    if search_name in unserved:
        raise _refusal(ctx, criterion_id, search_name)
    listed = await search_record_types(ctx.deps.site_id, [search_name])
    if search_name not in listed:
        unserved[search_name] = UnservedSearch(
            where=_ANY_RECORD_TYPE, said="the site's catalog lists it under none"
        )
        raise _refusal(ctx, criterion_id, search_name)
    return listed[search_name]


@contextmanager
def an_unserved_search_refused(
    ctx: RunContext[AgentDeps], criterion_id: str, search_name: str, record_type: str
) -> Iterator[None]:
    try:
        yield
    except VEuPathDBError as exc:
        not_found = _not_found_in(exc)
        if not_found is None:
            raise
        said = f"HTTP {not_found.status}: {not_found.detail}"
        state = ctx.deps.agent_state
        state.refused_searches[search_name] = (
            f"HTTP {not_found.status} under record type {record_type}: "
            f"{not_found.detail}"
        )
        state.unserved_searches[search_name] = UnservedSearch(
            where=record_type, said=said
        )
        raise _refusal(ctx, criterion_id, search_name) from exc


def _not_found_in(error: BaseException | None) -> WDKError | None:
    match error:
        case WDKError(status=HTTPStatus.NOT_FOUND):
            return error
        case None:
            return None
        case _:
            return _not_found_in(error.__cause__)


def _refusal(
    ctx: RunContext[AgentDeps], criterion_id: str, search_name: str
) -> ModelRetry:
    unserved = ctx.deps.agent_state.unserved_searches
    held = unserved[search_name]
    held.refusals += 1
    named = sum(search.refusals for search in unserved.values())
    sentence = held.sentence(search_name, ctx.deps.site_id)
    if named > DEFAULT_REPETITION_THRESHOLD:
        msg = (
            f"{sentence} This pass named a search the site does not serve "
            f"{named} times and stops here."
        )
        raise SearchNotServedError(msg)
    if held.where == _ANY_RECORD_TYPE:
        return ModelRetry(
            f"{sentence} {criterion_id} is not bound. Bind a search that "
            "list_searches or search_for_searches answered with; a requirement "
            "no search on this site answers is site_has_no_search."
        )
    return ModelRetry(
        f"{sentence} {criterion_id} is not bound, and this pass binds "
        f"{search_name} no more. Bind another search for this requirement; a "
        f"requirement only {search_name} answers is site_refused_the_search, "
        f"with {search_name} named."
    )
