from __future__ import annotations

from datetime import date

from veupathdb_mcp.catalog import PhyleticPattern
from veupathdb_mcp.wdk import ComputedComparisonResult

from pathfinder.domain.strategy.computed_groups import HeldComparison

GROUP_IDS = ("OG7_0000001", "OG7_0000002", "OGR7r1_0000123")
COMPARISON = ComputedComparisonResult.model_validate(
    {
        "siteId": "orthomcl",
        "reading": "the per-genome average proteins of TOXO more than those of PLAS",
        "groups": 3,
        "groupIds": list(GROUP_IDS),
        "bothHeld": 2,
        "leftOnly": 1,
        "rightOnly": 0,
        "ties": 1,
        "residualGroups": 1,
        "sets": [
            {
                "side": "left",
                "genomes": 2,
                "species": [{"species": "Toxoplasma gondii", "genomes": 2}],
                "groups": 3,
                "proteins": 9,
            },
            {
                "side": "right",
                "genomes": 3,
                "species": [
                    {"species": "Plasmodium falciparum", "genomes": 2},
                    {"species": "Plasmodium vivax", "genomes": 1},
                ],
                "groups": 2,
                "proteins": 4,
            },
        ],
        "probeRequests": 0,
        "computeRequests": 6,
    }
)


def held_comparison(pattern: PhyleticPattern, computed_on: date) -> HeldComparison:
    return HeldComparison(pattern=pattern, answer=COMPARISON, computed_on=computed_on)
