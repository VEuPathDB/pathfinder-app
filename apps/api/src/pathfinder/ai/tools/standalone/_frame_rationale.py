"""Why a criterion runs its search: the argument FRAME passes, and the record
the tool writes from the catalog read this pass holds.

Every claim in the argument is checked against data the call holds. No check
reads a similarity threshold; ``nearest`` compares hits of one read.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from pydantic_ai import ModelRetry, RunContext
from veupathdb.domain.parameters import ParamValue, to_wire
from veupathdb_mcp import tool_payloads
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import CatalogHit, CatalogRead
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._frame_proposals import (
    ParamProposals,
    _CriterionCall,
)
from pathfinder.domain.strategy.step_rationale import (
    ComparedSearch,
    RationaleBasis,
    SearchRationale,
    names_the_phrase,
)

_COMPARED = 3


class SearchChoice(CamelModel):
    """Why this search and not the others the catalog answered for this criterion."""

    basis: RationaleBasis = Field(
        description=(
            "parameter: a parameter of this search carries the requested value. "
            "organism: the search covers the organism the request names. "
            "record_type: it returns the record type the request asks for. "
            "only_match: no other search the catalog answered names the term. "
            "nearest: no search states the request; this one scored closest."
        )
    )
    term: str = Field(
        description=(
            "parameter: the parameter name you set. organism: the organism value "
            "you set. record_type: the record type. only_match and nearest: the "
            "phrase from the request."
        )
    )
    reason: str = Field(
        max_length=160,
        description=(
            "One line, holding the term. Name another search only if the catalog "
            "answered it."
        ),
    )
    sources: list[str] = Field(
        default_factory=list,
        description=(
            "The urls, DOIs or PMIDs a research read of this turn returned that "
            "the choice rests on. Empty when it rests on the catalog alone."
        ),
    )


@dataclass(frozen=True)
class _Binding:
    """What one binding call holds for the checks: the read and the values."""

    criterion_id: str
    search_name: str
    record_type: str
    read: CatalogRead
    bound: CatalogHit
    infos: Sequence[ParameterInfo]
    params: ParamProposals
    values: Mapping[str, ParamValue]


async def rationale_for(
    ctx: RunContext[AgentDeps],
    call: _CriterionCall,
    record_type: str,
    infos: Sequence[ParameterInfo],
    values: Mapping[str, ParamValue],
    why: SearchChoice | None,
) -> SearchRationale | None:
    """The recorded reason for this binding, or a retry naming what is wrong.

    A value edit on the search the criterion already runs keeps its reason.
    """
    criterion_id, search_name = call.criterion_id, call.search_name
    state = ctx.deps.agent_state
    held = next(
        (c for c in state.operational_spec_draft.criteria if c.id == criterion_id),
        None,
    )
    if why is None and held is not None and held.search_name == search_name:
        return held.rationale
    read = state.last_read_answering(search_name)
    bound = None if read is None else read.hit(search_name)
    if read is None or bound is None:
        raise ModelRetry(_unread(criterion_id, search_name))
    if why is None:
        raise ModelRetry(_no_why(criterion_id, search_name, read))
    listing = await tool_payloads.list_search_listings(ctx.deps.site_id, record_type)
    listed = [(search.name, search.display_name) for search in listing]
    unseen = _unseen_mentions(why.reason, read, listed)
    if unseen:
        raise ModelRetry(_unseen(criterion_id, unseen, read))
    binding = _Binding(
        criterion_id=criterion_id,
        search_name=search_name,
        record_type=record_type,
        read=read,
        bound=bound,
        infos=infos,
        params=call.params,
        values=values,
    )
    term = _checked_term(why, binding)
    held_terms = [why.term, term]
    if not any(names_the_phrase(why.reason, t) for t in held_terms):
        raise ModelRetry(_reason_without_term(criterion_id, term))
    others = [h for h in read.hits if h.name != search_name] if read.ranked else []
    return SearchRationale(
        search_name=search_name,
        basis=why.basis,
        term=term,
        reason=why.reason,
        similarity=bound.similarity,
        compared=[
            ComparedSearch(
                name=h.name, display_name=h.display_name, similarity=h.similarity
            )
            for h in others[:_COMPARED]
        ],
        answered=len(read.hits),
        query=read.query,
        tool_call_id=read.tool_call_id,
        sources=_retrieved(ctx, criterion_id, why.sources),
    )


def _checked_term(why: SearchChoice, at: _Binding) -> str:
    """The term as the researcher reads it, once the data backs the basis."""
    cid, term = at.criterion_id, why.term
    match why.basis:
        case "parameter":
            return _set_parameter(cid, term, at)
        case "organism":
            if not any(
                term.casefold() in to_wire(v).casefold() for v in at.values.values()
            ):
                msg = (
                    f"{cid}: no value this binding sends holds {term}, so the "
                    f"organism does not decide the choice."
                )
                raise ModelRetry(msg)
        case "record_type":
            _refuse_a_record_type_that_decides_nothing(cid, term, at)
        case "only_match":
            _refuse_a_shared_term(cid, term, at)
        case "nearest":
            _refuse_a_nearer_hit(cid, term, at)
    return term


def _set_parameter(cid: str, term: str, at: _Binding) -> str:
    """The display name of the parameter this call set, which the term names."""
    wanted = term.casefold()
    info = next(
        (
            i
            for i in at.infos
            if wanted in {i.name.casefold(), i.display_name.casefold()}
        ),
        None,
    )
    if info is None:
        names = ", ".join(i.name for i in at.infos)
        msg = (
            f"{cid}: {term} is not a parameter of {at.search_name}; its sheet "
            f"holds {names}."
        )
        raise ModelRetry(msg)
    if at.params.get(info.name) is None:
        msg = (
            f"{cid}: this call leaves {term} null, so it decides nothing. Name the "
            f"parameter whose value decides the choice."
        )
        raise ModelRetry(msg)
    return info.display_name


def _refuse_a_record_type_that_decides_nothing(
    cid: str, term: str, at: _Binding
) -> None:
    if term.casefold() != at.record_type.casefold():
        msg = f"{cid}: {at.search_name} returns {at.record_type}, not {term}."
        raise ModelRetry(msg)
    if all(h.record_type == at.record_type for h in at.read.hits):
        msg = (
            f"{cid}: every search the catalog answered returns {term}, so the "
            f"record type decides nothing. Give the basis that does."
        )
        raise ModelRetry(msg)


def _refuse_a_shared_term(cid: str, term: str, at: _Binding) -> None:
    if not _names(at.bound, term):
        msg = (
            f"{cid}: the name and the description of {at.search_name} do not "
            f"hold {term}."
        )
        raise ModelRetry(msg)
    also = [
        h.display_name
        for h in at.read.hits
        if h.name != at.search_name and _names(h, term)
    ]
    if also:
        msg = f"{cid}: {', '.join(also)} also name {term}, so it is not the only match."
        raise ModelRetry(msg)


def _refuse_a_nearer_hit(cid: str, term: str, at: _Binding) -> None:
    """Nearest is an order inside one ranked read, never a threshold."""
    if not at.read.ranked or at.bound.similarity is None:
        msg = (
            f"{cid}: the read that answered {at.search_name} scored nothing, so it "
            f"cannot be the nearest to {term}. Rank it with search_for_searches, "
            f"or give another basis."
        )
        raise ModelRetry(msg)
    score = at.bound.similarity
    higher = [
        h.display_name
        for h in at.read.hits
        if h.similarity is not None and h.similarity > score
    ]
    if higher:
        msg = (
            f"{cid}: {', '.join(higher)} scored higher than {at.bound.display_name} "
            f"for '{at.read.query}', so it is not the nearest to {term}."
        )
        raise ModelRetry(msg)


def _names(hit: CatalogHit, term: str) -> bool:
    return names_the_phrase(hit.display_name, term) or names_the_phrase(
        hit.description, term
    )


def _unseen_mentions(
    reason: str, read: CatalogRead, listing: Sequence[tuple[str, str]]
) -> list[str]:
    """The site's searches the reason names that the read did not answer.

    A one-word display name is an ordinary word in a sentence, so it is not
    read as a mention.
    """
    answered = {h.name for h in read.hits}
    return [
        mention
        for name, display_name in listing
        if name not in answered
        for mention in (name, display_name)
        if (mention == name or len(mention.split()) > 1)
        and names_the_phrase(reason, mention)
    ]


def _retrieved(
    ctx: RunContext[AgentDeps], criterion_id: str, cited: Sequence[str]
) -> list[str]:
    """Each cited reference in the form a read of this turn returned it."""
    markers = ctx.deps.turn_markers
    found = {reference: markers.retrieved_as(reference) for reference in cited}
    absent = [reference for reference, form in found.items() if form is None]
    if absent:
        msg = (
            f"The why of {criterion_id} cites {', '.join(absent)}, and no read of "
            f"this turn returned it. Cite only what a research read returned this "
            f"turn, or leave sources empty; nothing was recorded."
        )
        raise ModelRetry(msg)
    return [form for form in found.values() if form is not None]


def _top(read: CatalogRead) -> str:
    return ", ".join(
        ComparedSearch(
            name=h.name, display_name=h.display_name, similarity=h.similarity
        ).label()
        for h in read.hits[:_COMPARED]
    )


def _unread(criterion_id: str, search_name: str) -> str:
    return (
        f"{criterion_id} binds {search_name}, which no catalog read of this pass "
        f"answered. Call search_for_searches for what {criterion_id} asks, then "
        f"bind from its answer; the choice is recorded against the searches it "
        f"returned. Nothing was recorded."
    )


def _no_why(criterion_id: str, search_name: str, read: CatalogRead) -> str:
    return (
        f"{criterion_id} binds {search_name} with no why. Pass why with a basis "
        f"(parameter, organism, record_type, only_match or nearest), the term "
        f"that decides it, and one line of reason holding the term. The catalog "
        f"answered {len(read.hits)} searches for it, first {_top(read)}. "
        f"Nothing was recorded."
    )


def _unseen(criterion_id: str, unseen: Sequence[str], read: CatalogRead) -> str:
    answered = ", ".join(h.display_name for h in read.hits)
    return (
        f"Your reason for {criterion_id} names {', '.join(unseen)}, which the "
        f"catalog did not answer for it. It answered: {answered}. Give the reason "
        f"in terms of those, or search again. Nothing was recorded."
    )


def _reason_without_term(criterion_id: str, term: str) -> str:
    return (
        f"{criterion_id}: the reason does not hold the term {term}. Write the "
        f"reason around it, so a reply that repeats it says what decided. "
        f"Nothing was recorded."
    )
