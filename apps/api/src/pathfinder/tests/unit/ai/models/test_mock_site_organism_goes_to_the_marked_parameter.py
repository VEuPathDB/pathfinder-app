"""A canned criterion no seed values puts the site organism on the parameter the
pinned sheet marks as the organism, whatever its name."""

from __future__ import annotations

from veupathdb_mcp.catalog import SheetEntry

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.agents.strategy_instructions import pinned_frame_sheets
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.specs import CriterionSpec, proposal_args
from pathfinder.ai.models.mock.strategy_specs import seed_criterion
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_LOCATION = "GenesByLocation"
_NO_SEED = "GenesByNoSeedSearch"


def _pinned(criterion_id: str, search_name: str) -> str:
    """The pinned sheet of a search whose organism parameter is organismSinglePick."""
    state = AgentToolState()
    sheet = [
        SheetEntry(
            name="organismSinglePick",
            display_name="Organism",
            type="single-pick-vocabulary",
            required=True,
            organism_param=True,
        ),
        SheetEntry(
            name="chromosome", display_name="Chromosome", type="string", required=True
        ),
    ]
    state.pin_sheet(criterion_id, search_name, sheet, what_runs=search_name)
    return pinned_frame_sheets(agent_run_context(agent_state=state)) or ""


def test_an_unseeded_criterion_holds_the_site_organism_under_no_name() -> None:
    values = SiteValues.for_site("vectorbase")

    crit = seed_criterion(values, _NO_SEED, "c_located", "genes on chromosome 2L")

    assert (crit.values, crit.site_organism) == ({}, values.organism)


def test_the_proposal_values_the_marked_organism_parameter() -> None:
    crit = CriterionSpec(
        criterion_id="c_located",
        text="genes on chromosome 2L",
        search_name=_LOCATION,
        values={"chromosome": "2L"},
        site_organism="Anopheles gambiae PEST",
    )
    sheet = dict.fromkeys(["organismSinglePick", "chromosome"])

    args = proposal_args(crit, sheet, _pinned("c_located", _LOCATION))

    assert args["params"] == {
        "organismSinglePick": ["Anopheles gambiae PEST"],
        "chromosome": "2L",
    }


def test_a_stated_organism_value_is_kept() -> None:
    crit = CriterionSpec(
        criterion_id="c_located",
        text="genes on chromosome 2L",
        search_name=_LOCATION,
        values={"organismSinglePick": ["Anopheles stephensi Indian"]},
        site_organism="Anopheles gambiae PEST",
    )
    sheet = dict.fromkeys(["organismSinglePick", "chromosome"])

    args = proposal_args(crit, sheet, _pinned("c_located", _LOCATION))

    assert args["params"] == {
        "organismSinglePick": ["Anopheles stephensi Indian"],
        "chromosome": None,
    }
