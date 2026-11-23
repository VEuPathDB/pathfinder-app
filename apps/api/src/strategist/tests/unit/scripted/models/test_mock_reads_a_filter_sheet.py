"""The mock FRAME reads a pinned sheet that holds a filter parameter."""

from __future__ import annotations

from veupathdb.domain.parameters import FilterFacet, VocabOption
from veupathdb_mcp.catalog import SheetEntry

from strategist.ai.agents.state import PinnedSheet
from strategist.ai.agents.strategy_instructions import pinned_frame_sheets
from strategist.tests.unit.ai.tools.conftest import agent_run_context
from strategist_scripted.models.sheets import sheet_entries

PEST = "Anopheles gambiae PEST"
GENE_MODEL = PinnedSheet(
    search_name="GenesByGeneModelChars",
    opened=True,
    entries=[
        SheetEntry(
            name="gene_model_char",
            display_name="Gene model characteristics",
            type="filter",
            required=True,
            filter_facets=[
                FilterFacet(
                    term="organism",
                    display="Organism",
                    parent=None,
                    type="string",
                    is_range=False,
                    units=None,
                    precision=0,
                    members=[],
                )
            ],
        ),
        SheetEntry(
            name="organism_select_none",
            display_name="Organism",
            type="multi-pick-vocabulary",
            required=True,
            organism_param=True,
            vocabulary=[VocabOption(value=PEST, display=PEST)],
        ),
    ],
)


def test_a_sheet_with_a_filter_parameter_is_read_back() -> None:
    ctx = agent_run_context(site_id="vectorbase")
    ctx.deps.agent_state.open_sheets["organism_genes"] = GENE_MODEL

    entries = sheet_entries(pinned_frame_sheets(ctx) or "", "organism_genes")

    assert [(e.name, e.organism_param) for e in entries] == [
        ("gene_model_char", False),
        ("organism_select_none", True),
    ]
    assert [option.value for option in entries[1].vocabulary] == [PEST]
