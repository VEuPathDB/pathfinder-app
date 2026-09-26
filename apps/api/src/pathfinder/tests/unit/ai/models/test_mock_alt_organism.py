"""The second organism of an arc is read from the sheet FRAME's instructions pin."""

from __future__ import annotations

import pytest
from veupathdb_mcp.catalog import build_sheet, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.agents.strategy_instructions import pinned_frame_sheets
from pathfinder.ai.models.mock.sheets import alt_organism
from pathfinder.tests._support.recorded_searches import suite_search
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context


def _pinned(fixture: str, search_name: str, criterion_id: str) -> str:
    definition = suite_search(fixture)
    entries = build_sheet(
        format_param_info_typed(definition.parameters or []), query="orthologs"
    )
    state = AgentToolState()
    state.pin_sheet(criterion_id, search_name, entries, what_runs=search_name)
    return pinned_frame_sheets(agent_run_context(agent_state=state)) or ""


def test_the_second_organism_is_a_strain_of_the_same_genus() -> None:
    pinned = _pinned("search_genes_by_orthologs_vectorbase", "GenesByOrthologs", "c1")

    alt = alt_organism(pinned, "c1", "Anopheles gambiae PEST", same_genus=True)

    assert alt == "Anopheles albimanus STECLA"


def test_the_second_organism_can_be_a_strain_of_another_genus() -> None:
    pinned = _pinned("search_genes_by_orthologs_vectorbase", "GenesByOrthologs", "c1")

    alt = alt_organism(pinned, "c1", "Anopheles gambiae PEST", same_genus=False)

    assert alt == "Amblyomma americanum F_SG_1"


def test_the_taxon_sheet_gives_a_plasmodium_strain() -> None:
    pinned = _pinned("search_genes_by_taxon", "GenesByTaxon", "seed")

    assert alt_organism(
        pinned, "seed", "Plasmodium falciparum 3D7", same_genus=True
    ) == ("Plasmodium adleri G01")


def test_a_criterion_with_no_pinned_sheet_fails_loudly() -> None:
    pinned = _pinned("search_genes_by_taxon", "GenesByTaxon", "seed")

    with pytest.raises(LookupError, match="other"):
        alt_organism(pinned, "other", "Plasmodium falciparum 3D7", same_genus=True)
