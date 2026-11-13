from __future__ import annotations

from strategist.ai.lead.organism_reader import named_organisms
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    OrthologValue,
)

_ENTRIES = ["Plasmodium vivax P01", "Plasmodium falciparum 3D7"]


def _orthologs(*organisms: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.ORTHOLOG,
        requested_value="orthologs",
        label="orthologs",
        quote="their orthologs in P. vivax P01 and in Homo sapiens",
        source=ConstraintSource.USER_EXPLICIT,
        value=OrthologValue(organisms=list(organisms)),
    )


async def test_each_ortholog_organism_the_site_lists_is_its_entry() -> None:
    named = await named_organisms(
        "plasmodb",
        [_orthologs("P. vivax P01", "Homo sapiens")],
        "their orthologs in P. vivax P01 and in Homo sapiens",
        _ENTRIES,
    )

    [held] = named.constraints
    assert held.value == OrthologValue(
        organisms=["Plasmodium vivax P01", "Homo sapiens"]
    )
    assert named.picks == []
