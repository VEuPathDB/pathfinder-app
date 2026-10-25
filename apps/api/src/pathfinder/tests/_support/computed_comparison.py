from __future__ import annotations

from datetime import date
from uuid import uuid4

from pydantic import TypeAdapter
from veupathdb_mcp.catalog import PhyleticPattern
from veupathdb_mcp.wdk import ComputedComparisonResult

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, apply_agent_state
from pathfinder.ai.tools.standalone.orthomcl_expressions import (
    ComputedComparison,
    build_phyletic_expression,
)
from pathfinder.domain.strategy.computed_groups import HeldComparison
from pathfinder.tests._support.orthomcl_clouds import genus_mean, served_genus_clouds
from pathfinder.tests._support.orthomcl_counts import SITE
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

PATTERN: PhyleticPattern = TypeAdapter(PhyleticPattern).validate_python(
    {
        "kind": "compare",
        "left": {"kind": "codes", "codes": ["aaaa"]},
        "right": {"kind": "codes", "codes": ["bbbb"]},
        "reading": "averages",
        "condition": "more_than",
    }
)

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


async def framed_comparison() -> tuple[LeadDeps, ComputedComparison]:
    deps = lead_deps(pipeline_state(SITE, user_message_id=uuid4()))
    state = AgentToolState()
    with served_genus_clouds():
        result = await build_phyletic_expression(
            agent_run_context(site_id=SITE, agent_state=state), genus_mean()
        )
    apply_agent_state(deps, agent_run_context(site_id=SITE, agent_state=state).deps)
    return deps, returned(result, ComputedComparison)
