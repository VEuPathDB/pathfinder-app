from uuid import uuid4

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.orthology import OrganismChange
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_CARRIED = OrganismChange(
    seed=["Plasmodium falciparum 3D7"], records=["Plasmodium vivax P01"]
)


def _built(change: OrganismChange | None, *, changed: bool = True) -> LeadDeps:
    state = pipeline_state(
        user_prompt="Carry these to their orthologs in Plasmodium vivax P01.",
        user_message_id=uuid4(),
    )
    state.record_build(
        BuildOutcome(pushed_step_ids=["s1", "s2"], organism_change=change)
    )
    state.turn_markers.built = changed
    return lead_deps(state)


def _organism_sentences(deps: LeadDeps) -> list[str]:
    caveats = turn_facts(deps).caveats
    return [c.sentence for c in caveats if c.kind == "records_organism"]


def test_records_carried_to_another_organism_are_named_with_the_seed() -> None:
    assert _organism_sentences(_built(_CARRIED)) == [
        (
            "The strategy's records are genes of Plasmodium vivax P01; the seed "
            "searched Plasmodium falciparum 3D7"
        )
    ]


def test_a_round_trip_names_no_organism() -> None:
    assert _organism_sentences(_built(None)) == []


def test_a_turn_that_changed_nothing_names_no_organism() -> None:
    assert _organism_sentences(_built(_CARRIED, changed=False)) == []
