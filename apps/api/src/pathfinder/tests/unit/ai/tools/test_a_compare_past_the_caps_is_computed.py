"""A compare past one expression comes back computed from the group clouds, its
group ids held by handle and its counts read from the recorded clouds."""

from __future__ import annotations

from pydantic import TypeAdapter
from veupathdb_mcp.catalog import PhyleticPattern

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone.orthomcl_expressions import (
    ComputedComparison,
    build_phyletic_expression,
)
from pathfinder.domain.strategy.computed_groups import comparison_handle
from pathfinder.tests._support.orthomcl_clouds import served_genus_clouds, set_codes
from pathfinder.tests._support.orthomcl_counts import SITE
from pathfinder.tests._support.tool_returns import returned

from .conftest import agent_run_context, summary_of

_PATTERN: TypeAdapter[PhyleticPattern] = TypeAdapter(PhyleticPattern)


def genus_mean() -> PhyleticPattern:
    codes = set_codes()
    return _PATTERN.validate_python(
        {
            "kind": "compare",
            "left": {"kind": "codes", "codes": sorted(codes.tox)},
            "right": {"kind": "codes", "codes": sorted(codes.plas)},
            "reading": "averages",
            "condition": "more_than",
        }
    )


async def test_the_genus_mean_is_computed_and_held_by_handle() -> None:
    state = AgentToolState()

    with served_genus_clouds() as site:
        result = await build_phyletic_expression(
            agent_run_context(site_id=SITE, agent_state=state), genus_mean()
        )

    computed = returned(result, ComputedComparison)
    assert (computed.route, computed.groups, computed.both_held) == (
        "computed",
        7364,
        1884,
    )
    assert (computed.left_only, computed.right_only, computed.ties) == (5480, 0, 371)
    assert (computed.residual_groups, computed.probe_requests) == (1969, 17)
    assert computed.compute_requests == 6
    held = state.computed_comparisons[computed.handle]
    assert (computed.handle, len(held.answer.group_ids)) == (
        comparison_handle(held.answer.group_ids),
        7364,
    )
    assert site.sent[17:] == [
        "groups",
        "groups",
        "cloud",
        "records",
        "cloud",
        "records",
    ]
    assert summary_of(result).data["summary"] == "7,364 groups, computed snapshot"


async def test_the_answer_names_each_set_and_its_leading_species() -> None:
    with served_genus_clouds():
        result = await build_phyletic_expression(
            agent_run_context(site_id=SITE), genus_mean()
        )

    left, right = returned(result, ComputedComparison).sets
    assert (left.genomes, left.groups, left.proteins) == (15, 8014, 140798)
    assert (right.genomes, right.groups, right.proteins) == (61, 9396, 333932)
    assert (right.species[0].species, right.species[0].genomes) == (
        "Plasmodium falciparum",
        20,
    )


async def test_the_group_ids_never_ride_the_tool_return() -> None:
    with served_genus_clouds():
        result = await build_phyletic_expression(
            agent_run_context(site_id=SITE), genus_mean()
        )

    dumped = returned(result, ComputedComparison).model_dump(by_alias=True)
    assert ("groupIds" in dumped, "group_ids" in dumped) == (False, False)
