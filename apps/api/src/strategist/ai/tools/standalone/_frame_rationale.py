"""Why a criterion runs its search: the argument FRAME passes, and the record
the tool writes from the catalog read this pass holds."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from pydantic_ai import RunContext
from veupathdb.domain.parameters import ParamValue
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.agents.state import AgentToolState, CatalogHit, CatalogRead
from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.tools.standalone._frame_proposals import (
    CriterionCall,
)
from strategist.domain.refusal import Problems, RefusalKey
from strategist.domain.strategy.expression_handles import stated_values
from strategist.domain.strategy.operational_spec import Criterion
from strategist.domain.strategy.step_rationale import (
    ComparedSearch,
    RationaleBasis,
    SearchRationale,
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
            "One line on what decided it; the term is shown before it. Name "
            "another search only if the catalog answered it."
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
    """The recorded reason, or the problems that leave the binding without one."""

    rationale: SearchRationale | None
    problems: Problems = field(default_factory=Problems)


_WHY = RefusalKey(check="why")


def _held_rationale(state: AgentToolState, call: CriterionCall) -> bool:
    return any(
        c.id == call.criterion_id and c.search_name == call.search_name
        for c in state.operational_spec_draft.criteria
    )


def why_problems(
    ctx: RunContext[AgentDeps], call: CriterionCall, why: SearchChoice | None
) -> Problems:
    """What a new binding's why lacks before any value is read: a catalog read
    that answered the search, a why, and sources a read of this turn returned."""
    state = ctx.deps.agent_state
    if _held_rationale(state, call):
        return Problems()
    read = state.last_read_answering(call.search_name)
    if read is None or read.hit(call.search_name) is None:
        return Problems.one(_WHY, _unread(call.criterion_id, call.search_name))
    if why is None:
        return Problems.one(_WHY, _no_why(call.criterion_id, call.search_name, read))
    return sources_retrieved(ctx, call.criterion_id, why.sources)[1]


def rationale_for(
    ctx: RunContext[AgentDeps],
    call: CriterionCall,
    record_type: str,
    infos: Sequence[ParameterInfo],
    values: Mapping[str, ParamValue],
    why: SearchChoice | None,
) -> ChosenWhy:
    """The recorded reason for this binding, or the problems naming what is wrong.

    A binding on the search the criterion already runs keeps its reason while
    it changes no value the reason was derived from, or only an organism. One that changes such a value records the edit's
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
            changed = kept.changed_by(stated_values(values))
            organisms = {info.name for info in infos if info.organism_param}
            if not changed:
                return ChosenWhy(kept)
            if set(changed) <= organisms:
                rewired = kept.model_copy(
                    update={"derived_from": stated_values(values)}
                )
                return ChosenWhy(rewired)
            if why is None:
                said = _derived_from_changed(criterion_id, kept, changed)
                return ChosenWhy(None, Problems.one(_WHY, said))
            read = read or _read_behind(kept, held, record_type)
    return _new_why(ctx, call, read, why, infos, values)


def _new_why(
    ctx: RunContext[AgentDeps],
    call: CriterionCall,
    read: CatalogRead | None,
    why: SearchChoice | None,
    infos: Sequence[ParameterInfo],
    values: Mapping[str, ParamValue],
) -> ChosenWhy:
    criterion_id, search_name = call.criterion_id, call.search_name
    bound = None if read is None else read.hit(search_name)
    if read is None or bound is None:
        return ChosenWhy(None, Problems.one(_WHY, _unread(criterion_id, search_name)))
    if why is None:
        said = _no_why(criterion_id, search_name, read)
        return ChosenWhy(None, Problems.one(_WHY, said))
    sources, absent = sources_retrieved(ctx, criterion_id, why.sources)
    others = [h for h in read.hits if h.name != search_name] if read.ranked else []
    rationale = SearchRationale(
        search_name=search_name,
        basis=why.basis,
        term=_shown_term(why, infos),
        reason=why.reason,
        similarity=bound.similarity,
        compared=[
            ComparedSearch(
                name=h.name, display_name=h.display_name, similarity=h.similarity
            )
            for h in others[:_COMPARED]
        ],
        query=read.query,
        tool_call_id=read.tool_call_id,
        sources=sources,
        derived_from=stated_values(values),
    )
    return ChosenWhy(rationale, absent)


def _shown_term(why: SearchChoice, infos: Sequence[ParameterInfo]) -> str:
    if why.basis != "parameter":
        return why.term
    return next((i.display_name for i in infos if i.name == why.term), why.term)


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
        f"for the values this call binds."
    )


def sources_retrieved(
    ctx: RunContext[AgentDeps], criterion_id: str, cited: Sequence[str]
) -> tuple[list[str], Problems]:
    """Each cited reference in the form a read of this turn returned it, and
    the problem a reference no read returned makes."""
    markers = ctx.deps.turn_markers
    found = {reference: markers.retrieved_as(reference) for reference in cited}
    forms = [form for form in found.values() if form is not None]
    absent = [reference for reference, form in found.items() if form is None]
    if not absent:
        return forms, Problems()
    return forms, Problems.one(
        RefusalKey(check="sources"),
        f"The why of {criterion_id} cites {', '.join(absent)}, and no read of "
        f"this turn returned it. Cite only what a research read or "
        f"read_experiment returned this turn, or leave sources empty.",
    )


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
        f"returned."
    )


def _no_why(criterion_id: str, search_name: str, read: CatalogRead) -> str:
    return (
        f"{criterion_id} binds {search_name} with no why. Pass why with a basis "
        f"(parameter, organism, record_type, only_match or nearest), the term "
        f"that decides it, and one line of reason. The catalog answered "
        f"{len(read.hits)} searches for it, first {_top(read)}."
    )
