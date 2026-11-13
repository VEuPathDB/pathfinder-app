"""A computed comparison a framing pass made is a statistic of the thread: the
Lead reads its values and the facts part shows its breakdown."""

from __future__ import annotations

from datetime import date
from typing import cast

from langgraph.runtime import Runtime

from strategist.ai.graph import nodes
from strategist.ai.graph.runtime import Context
from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead.lead_pins import pinned_statistics
from strategist.ai.lead.turn_facts import turn_facts
from strategist.domain.statistic_facts import statistic_id
from strategist.tests._support.computed_comparison import (
    COMPARISON,
    PATTERN,
    framed_comparison,
    held_comparison,
)
from strategist.tests._support.run_context import run_context_for


async def test_the_facts_show_the_groups_and_the_breakdown() -> None:
    deps, _ = await framed_comparison()

    [shown] = turn_facts(deps).reads
    rows = {row.label: row.value for row in shown.rows}

    assert (
        rows["groups"],
        rows["both held"],
        rows["both held share"],
        rows["residual groups"],
    ) == ("7,364", "1,884", "25.6%", "1,969")


_HELD_BY = (
    "Of the 7,364 selected groups, 5,480 (74.4%) are held by the left set only "
    "(Toxoplasma gondii, 15 genomes), 1,884 (25.6%) by both sets and 0 (0%) by the "
    "right set only (23 species, 61 genomes)."
)


async def test_the_facts_lead_with_what_one_side_alone_holds() -> None:
    deps, _ = await framed_comparison()

    [shown] = turn_facts(deps).reads

    assert (shown.rows[0].label, shown.rows[0].value) == ("held by", _HELD_BY)


async def test_the_lead_reads_what_one_side_alone_holds_first() -> None:
    deps, _ = await framed_comparison()

    lines = (pinned_statistics(run_context_for(deps)) or "").splitlines()

    assert lines[3] == f"  - heldBy = {_HELD_BY}"


def _held(left_only: int, both_held: int, right_only: int) -> str:
    groups = left_only + both_held + right_only
    answer = COMPARISON.model_copy(
        update={
            "groups": groups,
            "group_ids": tuple(f"g{n}" for n in range(groups)),
            "left_only": left_only,
            "both_held": both_held,
            "right_only": right_only,
        }
    )
    held = held_comparison(PATTERN, date(2026, 1, 2)).model_copy(
        update={"answer": answer}
    )
    return held.facts().held_by


def test_the_largest_part_is_named_first() -> None:
    assert _held(1, 2, 7) == (
        "Of the 10 selected groups, 7 (70%) are held by the right set only (2 species, "
        "3 genomes), 2 (20%) by both sets and 1 (10%) by the left set only (Toxoplasma "
        "gondii, 2 genomes)."
    )
    assert _held(1, 7, 2) == (
        "Of the 10 selected groups, 7 (70%) are held by both sets, 2 (20%) by the right "
        "set only (2 species, 3 genomes) and 1 (10%) by the left set only (Toxoplasma "
        "gondii, 2 genomes)."
    )


def test_parts_of_one_size_keep_their_order() -> None:
    assert _held(2, 2, 2) == (
        "Of the 6 selected groups, 2 (33.3%) are held by the left set only (Toxoplasma "
        "gondii, 2 genomes), 2 (33.3%) by both sets and 2 (33.3%) by the right set only "
        "(2 species, 3 genomes)."
    )


async def test_the_lead_reads_the_route_and_the_leading_species() -> None:
    deps, computed = await framed_comparison()
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
    prefix = "  - "
    shown = {
        line.removeprefix(prefix).split(" = ")[0]: line.split(" = ")[1]
        for line in (pinned or "").splitlines()
        if line.startswith(prefix) and " = " in line
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
        [statistic_id("group_comparison", [computed.handle])],
    )
