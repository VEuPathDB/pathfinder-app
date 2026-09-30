"""A pick taken from a cut vocabulary list shows how many of the matching
entries it took on its own row, whoever set it."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
    ValueSource,
)
from pathfinder.domain.turn_facts import ParameterFact
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_DOMAINS = "domain_typeahead"
_NOTE = (
    "Specific Domain(s) took 50 of the 66 entries that match 'peptidase'; "
    "the list it was picked from showed only part of them"
)


def _row(source: ValueSource) -> ParameterFact:
    """The N. fowleri peptidase step, bound from a list cut at 50 of 66."""
    criterion = Criterion(
        id="c_peptidase",
        text="peptidases",
        search_name="GenesByInterproDomain",
        resolved_params={
            _DOMAINS: BoundValue(
                value=MultiPickValue(values=[f"PF{i:05d}" for i in range(50)]),
                source=source,
            )
        },
        param_display_names={_DOMAINS: "Specific Domain(s)"},
        measurements=[
            Measurement(
                kind="picked_from_a_cut_list",
                param=_DOMAINS,
                count=50,
                unchosen_count=16,
                reading="'peptidase'",
            )
        ],
        result_count=148,
    )
    state = pipeline_state(
        "amoebadb",
        domain=StrategyDomainState(
            operational_spec=OperationalSpec(criteria=[criterion])
        ),
    )
    [step] = turn_facts(lead_deps(state)).steps
    [row] = step.parameters
    return row


def test_a_chosen_pick_from_a_cut_list_says_n_of_m() -> None:
    assert _row("chosen").notes == [_NOTE]


def test_a_stated_pick_from_a_cut_list_says_n_of_m() -> None:
    assert _row("stated").notes == [_NOTE]
