"""Why a criterion runs its search: the argument FRAME passes, and the record
the tool writes from the catalog read this pass holds.

Every claim in the argument is checked against data the call holds. No check
reads a similarity threshold; ``nearest`` compares hits of one read.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
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
    CriterionCall,
)
from pathfinder.ai.tools.standalone._frame_rationale_terms import (
    Binding,
    checked_term,
)
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.step_rationale import (
    MAX_REASON_CHARS,
    ComparedSearch,
    RationaleBasis,
    SearchRationale,
    names_the_phrase,
)
from pathfinder.domain.strategy.words import FILLER_WORDS, words_of

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
            "parameter: the name or display name of the parameter you set, never "
            "its value. organism: the organism value you set. record_type: the "
            "record type. only_match and nearest: the phrase from the request. "
            "A call that sets a value away from its default besides the organism "
            "names that parameter with basis parameter, even when the edit "
            "changes only the organism; the organism goes in the reason."
        )
    )
    reason: str = Field(
        description=(
            f"One line of at most {MAX_REASON_CHARS} characters on what decided it; "
            "the term is shown before it. Name another search only if the catalog "
            "answered it."
        ),
    )
    sources: list[str] = Field(
        default_factory=list,
        description=(
            "The urls, DOIs or PMIDs a research read or read_experiment returned "
            "this turn that the choice rests on. Empty when it rests on the "
            "catalog alone."
        ),
    )


@dataclass(frozen=True)
class ChosenWhy:
    """The recorded reason, and the rewrites the tool applied to reach it."""

    rationale: SearchRationale | None
    corrections: tuple[str, ...] = ()


async def rationale_for(
    ctx: RunContext[AgentDeps],
    call: CriterionCall,
    record_type: str,
    infos: Sequence[ParameterInfo],
    values: Mapping[str, ParamValue],
    why: SearchChoice | None,
    *,
    defaulted: Collection[str],
    transform: bool,
) -> ChosenWhy:
    """The recorded reason for this binding, or a retry naming what is wrong.

    A binding on the search the criterion already runs keeps its reason while
    it changes no value the reason was derived from, or only an organism the
    reason does not name. One that changes such a value records the edit's
    why, checked like a new one against the catalog read the reason holds, and
    is refused without one.
    """
    criterion_id, search_name = call.criterion_id, call.search_name
    state = ctx.deps.agent_state
    held = next(
        (c for c in state.operational_spec_draft.criteria if c.id == criterion_id),
        None,
    )
    read = state.last_read_answering(search_name)
    # The counts of a criterion the controls chose belong to the values they
    # measured, so an edit of those values states a reason of its own.
    if held is not None and held.search_name == search_name:
        kept = held.rationale
        if kept is None:
            return ChosenWhy(None)
        if kept.kind == "search":
            changed = kept.changed_by(_wired(values))
            organisms = {info.name for info in infos if info.organism_param}
            if not changed:
                return ChosenWhy(kept)
            if set(changed) <= organisms and not _names_the_old_value(kept, changed):
                rewired = kept.model_copy(update={"derived_from": _wired(values)})
                return ChosenWhy(rewired)
            if why is None:
                raise ModelRetry(_derived_from_changed(criterion_id, kept, changed))
            read = read or _read_behind(kept, held, record_type)
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
    binding = Binding(
        criterion_id=criterion_id,
        search_name=search_name,
        record_type=record_type,
        read=read,
        bound=bound,
        infos=infos,
        params=call.params,
        values=values,
        defaulted=defaulted,
        transform=transform,
    )
    chosen = checked_term(why.basis, why.term, binding)
    _refuse_a_long_reason(criterion_id, why, chosen.term)
    others = [h for h in read.hits if h.name != search_name] if read.ranked else []
    rationale = SearchRationale(
        search_name=search_name,
        basis=chosen.basis,
        term=chosen.term,
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
        sources=sources_retrieved(ctx, criterion_id, why.sources),
        derived_from=_wired(values),
    )
    corrections = () if chosen.correction is None else (chosen.correction,)
    return ChosenWhy(rationale, corrections)


def _names_the_old_value(kept: SearchRationale, changed: Sequence[str]) -> bool:
    """Whether the reason's words hold a word of a value this edit changes."""
    said = set(words_of(kept.sentence))
    return any(
        word in said
        for name in changed
        for word in words_of(kept.derived_from.get(name, ""))
        if word not in FILLER_WORDS
    )


def _wired(values: Mapping[str, ParamValue]) -> dict[str, str]:
    return {name: to_wire(value) for name, value in values.items()}


def _read_behind(
    kept: SearchRationale, held: Criterion, record_type: str
) -> CatalogRead:
    """The catalog read the kept reason recorded, as the searches it compared."""
    bound = CatalogHit(
        name=kept.search_name,
        display_name=held.search_display_name or kept.search_name,
        similarity=kept.similarity,
    )
    compared = [
        CatalogHit(name=c.name, display_name=c.display_name, similarity=c.similarity)
        for c in kept.compared
    ]
    return CatalogRead(
        tool_call_id=kept.tool_call_id,
        tool="search_for_searches" if kept.similarity is not None else "list_searches",
        query=kept.query,
        record_type=record_type,
        hits=[bound, *compared],
    )


def _derived_from_changed(
    criterion_id: str, kept: SearchRationale, changed: Sequence[str]
) -> str:
    held = ", ".join(
        f"{name} {kept.derived_from.get(name, '')}".strip() for name in changed
    )
    return (
        f"{criterion_id}: its reason was derived from {held}, which this edit "
        f"changes, so the reason no longer holds: '{kept.sentence}'. Pass a why "
        f"for the values this call binds. Nothing was recorded."
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


def sources_retrieved(
    ctx: RunContext[AgentDeps], criterion_id: str, cited: Sequence[str]
) -> list[str]:
    """Each cited reference in the form a read of this turn returned it."""
    markers = ctx.deps.turn_markers
    found = {reference: markers.retrieved_as(reference) for reference in cited}
    absent = [reference for reference, form in found.items() if form is None]
    if absent:
        msg = (
            f"The why of {criterion_id} cites {', '.join(absent)}, and no read of "
            f"this turn returned it. Cite only what a research read or "
            f"read_experiment returned this turn, or leave sources empty; nothing "
            f"was recorded."
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
        f"that decides it, and one line of reason of at most {MAX_REASON_CHARS} "
        f"characters. The catalog "
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


def _refuse_a_long_reason(criterion_id: str, why: SearchChoice, term: str) -> None:
    """A reason fits one line; the term is shown before it, so it need not repeat it."""
    if len(why.reason) <= MAX_REASON_CHARS:
        return
    msg = (
        f"{criterion_id}: the reason holds {len(why.reason)} characters. Write one "
        f"line of at most {MAX_REASON_CHARS} characters; the term {term} is shown "
        f"before it. Nothing was recorded."
    )
    raise ModelRetry(msg)
