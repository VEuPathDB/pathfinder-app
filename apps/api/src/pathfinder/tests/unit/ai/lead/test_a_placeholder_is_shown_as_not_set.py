"""A site placeholder left in a parameter is shown as not set, with no
measurement, since it states no value the search reads."""

from __future__ import annotations

from veupathdb.domain.parameters import StringValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
)
from pathfinder.domain.turn_facts import ParameterFact
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


def _location(value: str, *, placeholder: bool) -> list[ParameterFact]:
    """The hostdb chromosome 17 location step, its sequence id as the site left it."""
    criterion = Criterion(
        id="c_chr17",
        text="genes on chromosome 17",
        search_name="GenesByLocation",
        resolved_params={
            "sequenceId": BoundValue(
                value=StringValue(value=value),
                source="default",
                placeholder=placeholder,
            )
        },
        param_display_names={"sequenceId": "Genomic sequence ID"},
        measurements=[
            Measurement(
                kind="wildcard_phrase",
                param="sequenceId",
                count=2268,
                reading=f'"{value}"',
            )
        ],
        result_count=2268,
    )
    state = pipeline_state(
        "hostdb",
        domain=StrategyDomainState(
            operational_spec=OperationalSpec(criteria=[criterion])
        ),
    )
    [step] = turn_facts(lead_deps(state)).steps
    return step.parameters


def test_an_example_placeholder_is_not_set_and_not_measured() -> None:
    [row] = _location("(Example: chr22)", placeholder=True)

    assert row.lines() == ["Genomic sequence ID: not set (site placeholder)"]


def test_a_site_default_that_is_a_value_keeps_its_measurement() -> None:
    [row] = _location("17", placeholder=False)

    assert row.lines()[0] == "Genomic sequence ID: 17"
    assert len(row.notes) == 1


def test_a_parameter_the_site_sets_behind_the_sheet_draws_no_row() -> None:
    """microsporidiadb: the ecun exclusion's hidden profile pattern is no fact."""
    criterion = Criterion(
        id="c_orth",
        text="no ortholog in Encephalitozoon cuniculi GB-M1",
        search_name="GenesByOrthologPattern",
        resolved_params={
            "profile_pattern": BoundValue(
                value=StringValue(value="%ecun:N%"), source="stated"
            ),
            "excluded_species": BoundValue(
                value=StringValue(value="ecun"), source="stated"
            ),
        },
        param_display_names={
            "profile_pattern": "Profile Pattern",
            "excluded_species": "Excluded Species",
        },
        hidden_params=["profile_pattern"],
    )
    state = pipeline_state(
        "microsporidiadb",
        domain=StrategyDomainState(
            operational_spec=OperationalSpec(criteria=[criterion])
        ),
    )
    [step] = turn_facts(lead_deps(state)).steps

    assert [p.display_name for p in step.parameters] == ["Excluded Species"]
