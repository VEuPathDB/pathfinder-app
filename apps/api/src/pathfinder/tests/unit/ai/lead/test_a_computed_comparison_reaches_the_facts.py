"""A computed comparison a framing pass made is a statistic of the thread: the
Lead reads it by reference and a reply places its values."""

from __future__ import annotations

from typing import cast

from langgraph.runtime import Runtime

from pathfinder.ai.graph import nodes
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.lead_pins import pinned_statistics
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.reply_references import render_reply
from pathfinder.tests._support.computed_comparison import framed_comparison
from pathfinder.tests._support.run_context import run_context_for


async def test_a_reply_places_the_groups_and_the_breakdown() -> None:
    deps, computed = await framed_comparison()
    fact = computed.fact_id

    rendered = render_reply(
        f"The computed snapshot holds [stat:{fact}.groups] groups, "
        f"[stat:{fact}.bothHeld] held by both sets ([stat:{fact}.bothHeldShare]), "
        f"[stat:{fact}.residualGroups] of them residual.",
        turn_facts(deps),
    )

    assert rendered == (
        "The computed snapshot holds 7,364 groups, 1,884 held by both sets (25.6%), "
        "1,969 of them residual."
    )


async def test_the_lead_reads_the_route_and_the_leading_species() -> None:
    deps, computed = await framed_comparison()
    fact = computed.fact_id
    species = len(computed.sets[1].species)

    pinned = pinned_statistics(run_context_for(deps))

    names = (
        "route",
        "leftOnly",
        "rightOnly",
        "ties",
        "right.leadingSpecies",
        "right.leadingSpeciesGenomes",
        "right.leadingSpeciesShare",
        "right.genomes",
        "left.leadingSpeciesShare",
        "probeRequests",
        "computeRequests",
        "bothHeldShare",
        "leftOnlyShare",
        "rightOnlyShare",
        "residualGroupsShare",
    )
    prefix = f"  - [stat:{fact}."
    shown = {
        line.removeprefix(prefix).split("] = ")[0]: line.split("] = ")[1]
        for line in (pinned or "").splitlines()
        if line.startswith(prefix)
    }
    assert {name: shown[name] for name in names} == {
        "route": "computed snapshot",
        "leftOnly": "5,480",
        "rightOnly": "0",
        "ties": "371",
        "right.leadingSpecies": "Plasmodium falciparum",
        "right.leadingSpeciesGenomes": "20",
        "right.leadingSpeciesShare": "32.8%",
        "right.genomes": "61",
        "left.leadingSpeciesShare": "100%",
        "probeRequests": "17",
        "computeRequests": "6",
        "bothHeldShare": "25.6%",
        "leftOnlyShare": "74.4%",
        "rightOnlyShare": "0%",
        "residualGroupsShare": "26.7%",
    }
    assert [s.statements[1:] for s in deps.state.domain.statistics] == [
        [
            (
                "ties counts the 371 groups whose two sides are equal among every "
                "group either set holds, selected or not; it is no part of the "
                "selected groups."
            ),
            "Every genome of the left set is Toxoplasma gondii (15 genomes).",
            (
                "Plasmodium falciparum is 20 of the 61 genomes of the right set "
                f"(32.8%), the most of its {species} species."
            ),
        ]
    ]


async def test_the_turn_end_drops_the_ids_and_keeps_the_statistic() -> None:
    deps, computed = await framed_comparison()
    state = deps.state

    command = await nodes.finalize_turn_node(
        state, cast("Runtime[Context]", Runtime(context=None))
    )

    update = command.update
    assert isinstance(update, dict)
    domain = update["domain"]
    assert isinstance(domain, StrategyDomainState)
    assert (domain.computed_comparisons, [s.id for s in domain.statistics]) == (
        {},
        [computed.fact_id],
    )
