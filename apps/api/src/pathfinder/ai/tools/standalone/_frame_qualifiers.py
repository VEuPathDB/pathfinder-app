"""A word of the criterion text that narrows it binds a search that can state it.

The bound search, the searches this pass read and the parameter names of the
record type's searches are all read from WDK, so no word is named here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic_ai import ModelRetry, RunContext
from veupathdb.domain import SearchContext
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import fetch_search_details, get_raw_searches

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._frame_proposals import ParamProposals
from pathfinder.ai.tools.standalone._qualifier_words import (
    Qualifier,
    Statement,
    named_stems,
    proposal_values,
    qualifiers_of,
    spoken_stems,
    statements,
    stems_of,
    the_one_search_naming,
)
from pathfinder.domain.strategy.operational_spec import Criterion

_ROUND_TRIP = (
    " as a transform; to keep the source genes, state the round trip: the "
    "source INTERSECT a transform back to the source organism over a transform "
    "to the named organism over a copy of the source"
)


@dataclass(frozen=True)
class _Carried:
    """A qualifier the bound search cannot state, and a search of this pass that can."""

    qualifier: Qualifier
    search: WDKSearch
    through: list[Statement]


@dataclass(frozen=True)
class _Neighbours:
    """The definitions the site answered, and the searches it could not."""

    read: list[WDKSearch]
    unread: list[str]


@dataclass(frozen=True)
class QualifierCheck:
    """The words no search of the pass states, and the searches not compared."""

    unexpressed: list[str]
    unread: list[str]


@dataclass(frozen=True)
class _Reading:
    """The criterion's qualifiers, split by what the bound search does with them.

    ``spoken`` holds the words only a parameter of the bound search states, and
    ``held`` the stems whose one naming search is a search the pass read.
    """

    spoken: list[Qualifier]
    unspoken: list[Qualifier]
    held: frozenset[str]
    unread: list[str]


async def refuse_a_qualifier_the_search_drops(
    ctx: RunContext[AgentDeps],
    record_type: str,
    definition: WDKSearch,
    stated: Criterion,
) -> list[str]:
    """Refuse a search that cannot state a word of the criterion another search can.

    Returns the neighbouring searches the site could not answer.
    """
    reading = await _read(ctx, record_type, definition, stated)
    _, unread = await _refuse_a_search_another_one_outstates(
        ctx, record_type, definition, stated.id, reading
    )
    return unread


async def qualifiers_no_search_states(
    ctx: RunContext[AgentDeps],
    record_type: str,
    definition: WDKSearch,
    stated: Criterion,
    params: ParamProposals,
) -> QualifierCheck:
    """The criterion's words no search of this pass can state, once the binding
    states every word its own parameters can.

    A word only this binding's values carry, or that no search of the record
    type names a parameter by, is not one of them.
    """
    reading = await _read(ctx, record_type, definition, stated)
    left, unread = await _refuse_a_search_another_one_outstates(
        ctx, record_type, definition, stated.id, reading
    )
    _refuse_a_value_that_drops_a_qualifier(stated.id, definition, reading, params)
    valued = set().union(
        *(stems_of(v) for value in params.values() for v in proposal_values(value))
    )
    return QualifierCheck(
        unexpressed=[q.word for q in left if q.stem not in valued], unread=unread
    )


async def _read(
    ctx: RunContext[AgentDeps],
    record_type: str,
    definition: WDKSearch,
    stated: Criterion,
) -> _Reading:
    """The qualifiers of the text: the words exactly one search of the record
    type names a parameter by.

    A qualifier is held to a search only when the pass read the search that
    names it. A transform's text names the genes it maps, so a word the search
    of another criterion of the draft states belongs to that criterion and not
    to it.
    """
    naming = the_one_search_naming(
        await get_raw_searches(ctx.deps.site_id, record_type)
    )
    drafted = {
        c.search_name
        for c in ctx.deps.agent_state.operational_spec_draft.criteria
        if c.id != stated.id and c.search_name
    }
    others = _Neighbours(read=[], unread=[])
    if stated.role == "transform":
        others = await _definitions(ctx, record_type, drafted)
    claimed = frozenset().union(*(spoken_stems(other) for other in others.read))
    read = {
        definition.url_segment,
        *drafted,
        *_sibling_names(ctx, record_type, definition.url_segment),
    }
    qualifiers = [q for q in qualifiers_of(stated.text) if q.stem in naming]
    held = frozenset(q.stem for q in qualifiers if naming[q.stem] in read)
    spoken = spoken_stems(definition)
    # A word the search's own name states asks for the search itself.
    by_parameter = spoken - named_stems(definition)
    return _Reading(
        spoken=[q for q in qualifiers if q.stem in held & by_parameter],
        unspoken=[q for q in qualifiers if q.stem not in spoken | claimed],
        held=held,
        unread=others.unread,
    )


async def _refuse_a_search_another_one_outstates(
    ctx: RunContext[AgentDeps],
    record_type: str,
    definition: WDKSearch,
    criterion_id: str,
    reading: _Reading,
) -> tuple[list[Qualifier], list[str]]:
    """Refuse when a search this pass read states a held qualifier the bound
    one cannot.

    Returns the unspoken qualifiers no search of this pass states, and the
    searches the site could not answer.
    """
    if not reading.unspoken:
        return [], reading.unread
    own = [param.name for param in definition.parameters or []]
    siblings = await _siblings(ctx, record_type, definition.url_segment)
    carried: list[_Carried] = []
    left: list[Qualifier] = []
    for qualifier in reading.unspoken:
        found = next(
            (
                _Carried(qualifier, search, through)
                for search in siblings.read
                if (through := statements(search, qualifier.stem, besides=own))
            ),
            None,
        )
        if found is None:
            left.append(qualifier)
        elif qualifier.stem in reading.held:
            carried.append(found)
    if carried:
        raise ModelRetry(
            _outstated_message(criterion_id, definition, ctx.deps.site_id, carried)
        )
    return left, sorted({*reading.unread, *siblings.unread})


def _sibling_names(
    ctx: RunContext[AgentDeps], record_type: str, bound: str
) -> set[str]:
    """The searches of this record type the pass ranked or opened a sheet for."""
    state = ctx.deps.agent_state
    names = {
        hit.name
        for read in state.catalog_reads
        if read.ranked and read.record_type == record_type
        for hit in read.hits
    } | {sheet.search_name for sheet in state.open_sheets.values()}
    names.discard(bound)
    return names


async def _siblings(
    ctx: RunContext[AgentDeps], record_type: str, bound: str
) -> _Neighbours:
    """The definitions of the searches the pass ranked or opened a sheet for."""
    return await _definitions(ctx, record_type, _sibling_names(ctx, record_type, bound))


async def _definitions(
    ctx: RunContext[AgentDeps], record_type: str, names: set[str]
) -> _Neighbours:
    """The definitions of these searches of the record type, from the catalog."""
    each = await asyncio.gather(
        *(_definition(ctx.deps.site_id, record_type, name) for name in sorted(names))
    )
    return _Neighbours(
        read=[search for one in each for search in one.read],
        unread=[name for one in each for name in one.unread],
    )


async def _definition(site_id: str, record_type: str, name: str) -> _Neighbours:
    """One search's definition; a search the site cannot answer is only named."""
    try:
        response, owner = await fetch_search_details(
            SearchContext(site_id, record_type, name)
        )
    except VEuPathDBError:
        return _Neighbours(read=[], unread=[name])
    return _Neighbours(
        read=[response.search_data] if owner == record_type else [], unread=[]
    )


def _refuse_a_value_that_drops_a_qualifier(
    criterion_id: str,
    definition: WDKSearch,
    reading: _Reading,
    params: ParamProposals,
) -> None:
    """A parameter of the bound search that can state a qualifier states it."""
    for qualifier in reading.spoken:
        through = statements(definition, qualifier.stem)
        if not through or any(st.states(params.get(st.name)) for st in through):
            continue
        search = definition.display_name or definition.url_segment
        where = " or ".join(f"{st.display_name} ({st.name})" for st in through)
        how = " or ".join(f"{st.name} to {' or '.join(st.allowed)}" for st in through)
        msg = (
            f"{criterion_id} states '{qualifier.word}', and {search} states it "
            f"only through {where}, which this call leaves at its default or "
            f"switched off. Set {how}. Nothing was recorded."
        )
        raise ModelRetry(msg)


def _outstated_message(
    criterion_id: str,
    definition: WDKSearch,
    site_id: str,
    carried: Sequence[_Carried],
) -> str:
    search = definition.display_name or definition.url_segment
    words = ", ".join(f"'{c.qualifier.word}'" for c in carried)
    where = "; ".join(
        f"{c.search.display_name or c.search.url_segment} carries "
        f"'{c.qualifier.word}' ({', '.join(st.display_name for st in c.through)})"
        for c in carried
    )
    maps = any(c.search.allowed_primary_input_record_class_names for c in carried)
    return (
        f"{criterion_id}: {search} has no parameter that states {words}. On "
        f"{site_id}, {where}. Bind that search{_ROUND_TRIP if maps else ''}. "
        f"Nothing was recorded."
    )
