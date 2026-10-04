"""An organism pick a message names by its taxon is shown as that taxon with
its organism count, not as each organism it takes."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.named_taxa import NamedTaxon
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.turn_facts import ParameterFact
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.domain.strategy.test_a_taxon_the_message_names_takes_its_organisms import (
    BABESIA_LEAVES,
)


def _organism_row(taxon: NamedTaxon | None) -> ParameterFact:
    """The piroplasmadb taxon step, its organisms the ten Babesia leaves."""
    criterion = Criterion(
        id="c_babesia",
        text="genes across Babesia",
        search_name="GenesByTaxon",
        resolved_params={
            "organism": BoundValue(
                value=MultiPickValue(values=BABESIA_LEAVES),
                source="stated",
                basis="Babesia",
                taxon=taxon,
            )
        },
        param_display_names={"organism": "Organism"},
        result_count=41023,
    )
    state = pipeline_state(
        "piroplasmadb",
        domain=StrategyDomainState(
            operational_spec=OperationalSpec(criteria=[criterion])
        ),
    )
    [step] = turn_facts(lead_deps(state)).steps
    [row] = step.parameters
    return row


def test_a_named_taxon_is_shown_as_the_taxon_and_its_organism_count() -> None:
    row = _organism_row(NamedTaxon(name="Babesia", organisms=10))

    assert (row.lines(), row.source) == (["Organism: Babesia (10 organisms)"], "stated")


def test_a_pick_with_no_taxon_is_shown_as_its_organisms() -> None:
    row = _organism_row(None)

    assert row.lines() == [f"Organism: {', '.join(BABESIA_LEAVES)}"]
