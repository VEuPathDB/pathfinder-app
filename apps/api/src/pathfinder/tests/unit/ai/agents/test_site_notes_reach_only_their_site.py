from __future__ import annotations

from pathfinder.ai.agents.frame import _FRAME_INSTRUCTIONS
from pathfinder.ai.agents.site_notes import pinned_site_notes
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context


def test_the_orthomcl_notes_reach_an_orthomcl_pass() -> None:
    notes = pinned_site_notes(agent_run_context(site_id="orthomcl"))

    assert notes is not None
    assert "`build_phyletic_expression(pattern)`" in notes


def test_a_genomic_site_pass_reads_no_site_notes() -> None:
    assert [pinned_site_notes(agent_run_context(site_id="plasmodb"))] == [None]


def test_the_all_site_prompt_names_no_orthomcl_search() -> None:
    assert [
        name
        for name in ("GroupsByPhyleticPattern", "FromGroups", "ByTaxonomy")
        if name in _FRAME_INSTRUCTIONS
    ] == []
