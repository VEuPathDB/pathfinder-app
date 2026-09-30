"""A pick taken from a vocabulary read that showed only part of what matched
records how many of the matching entries it took, and the facts show it."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue
from veupathdb_mcp.catalog import PhrasingMatch, VocabLookup

from pathfinder.domain.strategy.measurement_clauses import measurement_clauses
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
)
from pathfinder.services.strategies.cut_picks import OptionsRead, read_picks

_DOMAINS = "domain_typeahead"
_SHOWN = [f"PF{i:05d}" for i in range(50)]
_LOOKUP = VocabLookup(
    terms=["peptidase"],
    matches=[
        PhrasingMatch(
            term="peptidase",
            phrasing="peptidase",
            reach="phrase",
            values=[*_SHOWN, *(f"PF9{i:04d}" for i in range(16))],
        )
    ],
)
_CUT = OptionsRead(param=_DOMAINS, shown=frozenset(_SHOWN), total=66, lookup=_LOOKUP)


def _bound(values: list[str]) -> dict[str, BoundValue]:
    return {_DOMAINS: BoundValue(value=MultiPickValue(values=values), source="chosen")}


def _picked(values: list[str]) -> Criterion:
    return Criterion(
        id="c_peptidase",
        text="peptidases with a signal peptide",
        search_name="GenesByInterproDomain",
        resolved_params=_bound(values),
    )


def test_a_pick_of_the_shown_entries_names_the_entries_it_could_not_see() -> None:
    assert read_picks(_picked(_SHOWN), [_CUT]) == [
        Measurement(
            kind="picked_from_a_cut_list",
            param=_DOMAINS,
            count=50,
            unchosen_count=16,
            reading="'peptidase'",
        )
    ]


def test_a_pick_that_reaches_past_the_shown_list_is_no_cut_pick() -> None:
    assert read_picks(_picked([*_SHOWN, "PF90000"]), [_CUT]) == []


def test_a_list_that_travelled_whole_is_no_cut_pick() -> None:
    whole = OptionsRead(param=_DOMAINS, shown=frozenset(_SHOWN), total=50, lookup=None)

    assert read_picks(_picked(_SHOWN), [whole]) == []


def test_the_clause_says_n_of_m() -> None:
    criterion = Criterion(
        id="c_peptidase",
        text="peptidases with a signal peptide",
        search_name="GenesByInterproDomain",
        resolved_params=_bound(_SHOWN),
        param_display_names={_DOMAINS: "Specific Domain(s)"},
        measurements=read_picks(_picked(_SHOWN), [_CUT]),
        result_count=148,
    )

    assert measurement_clauses(criterion, noun="gene") == [
        (
            "Specific Domain(s) took 50 of the 66 entries that match 'peptidase'; "
            "the list it was picked from showed only part of them"
        )
    ]
