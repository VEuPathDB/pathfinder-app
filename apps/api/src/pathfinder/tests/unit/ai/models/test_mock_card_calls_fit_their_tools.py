"""Every card call an arc makes fits the argument schema its tool advertises,
read from the tool itself, so a drift of either side fails here."""

from __future__ import annotations

import jsonschema_rs
import pytest
from pydantic_ai import Tool

from pathfinder.ai.lead.card_contract import CARD_TOOLS
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.models.mock.registry import ARCS
from pathfinder.ai.tools.standalone.optimization import optimize_search_parameters
from pathfinder.tests.unit.ai.models._mock_pins import framed_pins
from pathfinder.tests.unit.ai.models._mock_turns import (
    Scene,
    play,
)

SITES = ("plasmodb", "vectorbase")


def _lead_tools() -> dict[str, Tool[LeadDeps]]:
    """The Lead's own tools, and the sweep read from its signature."""
    sweep = Tool[LeadDeps](optimize_search_parameters)
    return {**build_lead_agent()._function_toolset.tools, sweep.name: sweep}


@pytest.mark.parametrize("site_id", SITES)
@pytest.mark.parametrize("framed", [False, True])
@pytest.mark.parametrize("arc", sorted(ARCS))
def test_every_card_call_fits_its_tool(arc: str, site_id: str, framed: bool) -> None:
    tools = _lead_tools()
    scene = Scene(instructions=framed_pins() if framed else "")

    calls = play("lead", site_id, f"Do it [[arc:{arc}]]", scene=scene)

    misfits = [
        (call.tool_name, str(error))
        for call in calls
        if call.tool_name in CARD_TOOLS
        for error in jsonschema_rs.validator_for(
            tools[call.tool_name].function_schema.json_schema
        ).iter_errors(call.args_as_dict())
    ]

    assert misfits == []


def test_the_proposal_card_is_checked() -> None:
    calls = play("lead", "plasmodb", "Offer one [[arc:proposal]]")

    assert [c.tool_name for c in calls if c.tool_name in CARD_TOOLS] == [
        "propose_changes"
    ]
