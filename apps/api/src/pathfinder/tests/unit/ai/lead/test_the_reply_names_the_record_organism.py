"""A reply about a strategy whose records moved to another organism names that
organism, in full or with the genus abbreviated."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.lead.reply_claims import names_an_organism
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.orthology import OrganismChange
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import kinds, reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_SOURCE = "Plasmodium falciparum 3D7"
_TARGET = "Plasmodium vivax P01"


def _built(change: OrganismChange | None) -> LeadDeps:
    state = pipeline_state(
        user_prompt="Carry these to their orthologs in Plasmodium vivax P01.",
        user_message_id=uuid4(),
    )
    state.record_build(
        BuildOutcome(
            pushed_step_ids=["s1", "s2"], root_count=67, organism_change=change
        )
    )
    state.turn_markers.verified = True
    return lead_deps(state)


_CARRIED = OrganismChange(seed=[_SOURCE], records=[_TARGET])


def test_a_count_without_the_organism_is_refused_with_the_organism() -> None:
    deps = _built(_CARRIED)

    mismatches = reconcile(
        reply("The strategy now holds 67 genes.", changed=True),
        turn_record(run_context_for(deps)),
    )

    found = [m.sentence for m in mismatches if m.kind == "unnamed_record_organism"]
    assert found == [
        (
            "The strategy's records are genes of Plasmodium vivax P01, and the seed "
            "searched Plasmodium falciparum 3D7. Your reply does not say whose "
            "genes these are. Name Plasmodium vivax P01 beside the count, in full "
            "or with the genus abbreviated."
        )
    ]


def test_the_abbreviated_genus_names_the_organism() -> None:
    deps = _built(_CARRIED)

    found = kinds(
        deps, reply("The strategy now holds 67 P. vivax P01 genes.", changed=True)
    )

    assert "unnamed_record_organism" not in found


def test_the_full_name_names_the_organism() -> None:
    deps = _built(_CARRIED)
    prose = f"The strategy now holds 67 genes of {_TARGET}."

    assert "unnamed_record_organism" not in kinds(deps, reply(prose, changed=True))


def test_a_round_trip_asks_nothing() -> None:
    deps = _built(None)

    found = kinds(deps, reply("The strategy now holds 67 genes.", changed=True))

    assert "unnamed_record_organism" not in found


def test_a_turn_that_changed_nothing_asks_nothing() -> None:
    deps = _built(_CARRIED)
    deps.state.turn_markers.built = False

    found = kinds(deps, reply("The strategy holds 67 genes.", changed=False))

    assert "unnamed_record_organism" not in found


def test_the_organism_is_read_whole_and_with_its_genus_abbreviated() -> None:
    assert names_an_organism("67 P. vivax P01 genes", _TARGET)
    assert names_an_organism("67 plasmodium vivax p01 genes", _TARGET)
    assert not names_an_organism("67 P. vivax genes", _TARGET)
    assert not names_an_organism("67 vivax P01 genes", _TARGET)
