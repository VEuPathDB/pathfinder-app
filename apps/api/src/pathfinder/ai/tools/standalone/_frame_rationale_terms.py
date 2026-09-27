"""The term a search choice names, checked against the values the binding call
sets and the catalog read it was chosen from."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import MultiPickValue, ParamValue, to_wire
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import CatalogHit, CatalogRead
from pathfinder.ai.tools.standalone._frame_proposals import ParamProposals
from pathfinder.domain.strategy.step_rationale import RationaleBasis, names_the_phrase


@dataclass(frozen=True)
class Binding:
    """What one binding call holds for the checks: the read and the values."""

    criterion_id: str
    search_name: str
    record_type: str
    read: CatalogRead
    bound: CatalogHit
    infos: Sequence[ParameterInfo]
    params: ParamProposals
    values: Mapping[str, ParamValue]
    defaulted: Collection[str]
    # A search that runs on an input step maps it to the organism it names.
    transform: bool


@dataclass(frozen=True)
class ChosenTerm:
    """The basis and the term the data backs."""

    basis: RationaleBasis
    term: str
    # How the call's own basis or term was rewritten to the one the data names.
    correction: str | None = None


def checked_term(basis: RationaleBasis, term: str, at: Binding) -> ChosenTerm:
    """The term as the researcher reads it, once the data backs the basis."""
    cid = at.criterion_id
    match basis:
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
            holding = {
                name
                for name, value in at.values.items()
                if term.casefold() in to_wire(value).casefold()
            }
            _refuse_the_organism_beside_a_set_value(cid, term, at, holding)
        case "record_type":
            _refuse_a_record_type_that_decides_nothing(cid, term, at)
        case "only_match":
            shared = _shared_term(cid, term, at)
            if shared is not None:
                raise ModelRetry(shared)
        case "nearest":
            _refuse_a_nearer_hit(cid, term, at)
    return ChosenTerm(basis, term)


def _set_parameter(cid: str, term: str, at: Binding) -> ChosenTerm:
    """The parameter the term names, or the one a value it equals is set on.

    A term naming the search itself, on a call that sets nothing but the
    organism, is the search's only match when no other hit names it.
    """
    wanted = term.casefold()
    info = next(
        (
            i
            for i in at.infos
            if wanted in {i.name.casefold(), i.display_name.casefold()}
        ),
        None,
    )
    if info is not None:
        return ChosenTerm("parameter", _checked_parameter(cid, term, at, info))
    holding = _set_with_value(term, at)
    if holding is not None:
        shown = holding.display_name
        return ChosenTerm(
            "parameter",
            _checked_parameter(cid, shown, at, holding),
            f"why.term corrected to {shown}: {term} is its value",
        )
    search = at.bound.display_name
    set_here = [i for i in at.infos if at.params.get(i.name) is not None]
    if (
        wanted in {at.search_name.casefold(), search.casefold()}
        and all(i.organism_param for i in set_here)
        and _shared_term(cid, search, at) is None
    ):
        return ChosenTerm(
            "only_match",
            search,
            f"why corrected to only_match on {search}: {term} names the search, "
            f"not a parameter",
        )
    raise ModelRetry(_not_a_parameter(cid, term, at))


def _set_with_value(term: str, at: Binding) -> ParameterInfo | None:
    """The one parameter this call sets to a value equal to the term, if one."""
    wanted = term.casefold()
    holding = [
        i
        for i in at.infos
        if at.params.get(i.name) is not None
        and i.name in at.values
        and wanted in {v.casefold() for v in _picks(at.values[i.name])}
    ]
    return holding[0] if len(holding) == 1 else None


def _picks(value: ParamValue) -> list[str]:
    """Each value a parameter holds: every pick of a multi-pick, else its wire form."""
    match value:
        case MultiPickValue(values=picks):
            return picks
        case _:
            return [to_wire(value)]


def _checked_parameter(cid: str, term: str, at: Binding, info: ParameterInfo) -> str:
    """The parameter's display name, once the call sets it and it may decide."""
    if at.params.get(info.name) is None:
        msg = (
            f"{cid}: this call leaves {term} null, so it decides nothing. Name the "
            f"parameter whose value decides the choice."
        )
        raise ModelRetry(msg)
    if info.organism_param:
        _refuse_the_organism_beside_a_set_value(cid, term, at, {info.name})
    return info.display_name


def _refuse_the_organism_beside_a_set_value(
    cid: str, term: str, at: Binding, organism: Collection[str]
) -> None:
    """The organism decides a binding only when no other value is set.

    A value set away from its default is what the binding asks, and one that
    sets nothing else is left to the structure fold. A transform's organism is
    where it maps, so it decides whatever else the call sets.
    """
    if at.transform:
        return
    set_away = [
        i.display_name
        for i in at.infos
        if i.is_visible
        and not i.organism_param
        and i.name not in organism
        and i.name in at.values
        and i.name not in at.defaulted
        and to_wire(at.values[i.name]) != i.default_value
    ]
    if not set_away:
        return
    named = ", ".join(set_away)
    msg = (
        f"{cid}: {term} is the organism the search runs on, and this call also "
        f"sets {named}, which is what decides the choice. Pass the term "
        f"'{set_away[0]}' with basis parameter, and keep the organism in the reason."
    )
    raise ModelRetry(msg)


def _not_a_parameter(cid: str, term: str, at: Binding) -> str:
    """Why the term names no parameter: the parameter a value is set on, or the
    display names the term may take."""
    set_here = [i for i in at.infos if at.params.get(i.name) is not None]
    holding = next(
        (
            i.display_name
            for i in set_here
            if i.name in at.values
            and term.casefold() in to_wire(at.values[i.name]).casefold()
        ),
        None,
    )
    if holding is not None:
        return (
            f"{cid}: {term} is a value this call sets on {holding}, not a "
            f"parameter. Pass the term '{holding}' with basis parameter, and keep "
            f"{term} in the reason."
        )
    names = ", ".join(i.display_name for i in set_here) or "none"
    return (
        f"{cid}: {term} is not a parameter of {at.search_name}. With basis "
        f"parameter the term is the display name of a parameter this call sets: "
        f"{names}. A value goes in the reason, never in the term."
    )


def _refuse_a_record_type_that_decides_nothing(
    cid: str, term: str, at: Binding
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


def _shared_term(cid: str, term: str, at: Binding) -> str | None:
    """Why the term is not the bound search's only match, or None when it is."""
    if not _names(at.bound, term):
        return (
            f"{cid}: the name and the description of {at.search_name} do not "
            f"hold {term}."
        )
    also = [
        h.display_name
        for h in at.read.hits
        if h.name != at.search_name and _names(h, term)
    ]
    if also:
        return (
            f"{cid}: {', '.join(also)} also name {term}, so it is not the only match."
        )
    return None


def _refuse_a_nearer_hit(cid: str, term: str, at: Binding) -> None:
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
