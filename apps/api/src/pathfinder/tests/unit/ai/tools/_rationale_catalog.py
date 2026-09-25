"""The GPI-anchor catalog read FRAME binds against, and the calls that bind.

The searches, their descriptions and the ExportPred sheet are PlasmoDB's own,
read from ``record-types/transcript/searches``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import VocabOption
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import ParameterInfo, SearchMatch

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.ai.tools.standalone.catalog import search_for_searches
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import (
    agent_run_context,
    serve_no_other_sites,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    param_info,
    serve_search,
    serve_site_listing,
)

WORDS = "genes with a predicted GPI anchor"
QUERY = "GPI anchor attachment signal"
ORGANISMS = [
    VocabOption(value="Plasmodium falciparum 3D7", display="P. falciparum 3D7"),
    VocabOption(value="Plasmodium vivax P01", display="P. vivax P01"),
]
PARAMS: dict[str, str | list[str] | None] = {
    "organism": ["Plasmodium falciparum 3D7"],
    "min_exportpred_score": None,
}


def match(
    name: str, display_name: str, description: str, similarity: float | None
) -> SearchMatch:
    return SearchMatch(
        name=name,
        display_name=display_name,
        description=description,
        record_type="transcript",
        relevance=1.0,
        semantic_similarity=similarity,
    )


EXPORTED = match(
    "GenesByExportPrediction",
    "Exported Protein",
    "Find genes that are predicted by ExportPred to produce an exported protein.",
    0.44,
)
SIGNAL = match(
    "GenesWithSignalPeptide",
    "Predicted Signal Peptide",
    "Find genes that are predicted to encode a secretory signal peptide "
    "containing protein.",
    0.41,
)
MEMBRANE = match(
    "GenesByTransmembraneDomains",
    "Transmembrane Domain Count",
    "Find genes whose protein products are predicted to have transmembrane "
    "domains numbering within a range that you specify.",
    0.36,
)
PATHWAY = SearchMatch(
    name="PathwaysByPathwayID",
    display_name="Pathway Name/ID",
    description="Find Pathways by Pathway Name.",
    record_type="pathway",
    relevance=0.5,
    semantic_similarity=0.2,
)
# The site's listing: the read's searches, and three it did not answer.
SITE = [
    {"name": m.name, "displayName": m.display_name}
    for m in (EXPORTED, SIGNAL, MEMBRANE)
] + [
    {"name": "GenesByTaxon", "displayName": "Organism"},
    {"name": "GenesByPhenotypeText", "displayName": "Phenotype Text"},
    {"name": "GenesByText", "displayName": "Text (product name, notes, etc.)"},
]


def export_pred_sheet(_context: dict[str, str]) -> list[ParameterInfo]:
    return [
        param_info(
            "organism",
            "multi-pick-vocabulary",
            display_name="Organism",
            vocab_leaves=ORGANISMS,
        ),
        param_info(
            "min_exportpred_score",
            display_name="Minimum ExportPred Score",
            required=False,
            default_value="10",
        ),
    ]


def serve_site(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ExportPred sheet, and the site's listing of transcript searches."""
    serve_search(monkeypatch, export_pred_sheet)
    serve_site_listing(monkeypatch, SITE)


async def read(
    monkeypatch: pytest.MonkeyPatch,
    state: AgentToolState,
    *matches: SearchMatch,
    call: str = "call_read",
    query: str = QUERY,
) -> None:
    monkeypatch.setattr(
        catalog, "search_for_searches", AsyncMock(return_value=list(matches))
    )
    serve_no_other_sites(monkeypatch)
    await search_for_searches(
        agent_run_context(agent_state=state, tool_call_id=call), query=query
    )


def choice(basis: str, term: str, reason: str, **fields: object) -> SearchChoice:
    return SearchChoice.model_validate(
        {"basis": basis, "term": term, "reason": reason, **fields}
    )


NEAREST = choice(
    "nearest",
    "GPI anchor",
    "no search states a GPI anchor; Exported Protein scored nearest",
)
ORGANISM = choice("parameter", "organism", "sets Organism to P. falciparum 3D7")


async def choose(
    state: AgentToolState,
    why: SearchChoice | None,
    *,
    search_name: str = EXPORTED.name,
    params: dict[str, str | list[str] | None] | None = None,
) -> SetCriterionResult:
    return returned(
        await set_criterion(
            frame_ctx(state),
            criterion_id="c_gpi",
            text=WORDS,
            search_name=search_name,
            params=dict(params or PARAMS),
            why=why,
        ),
        SetCriterionResult,
    )


async def refused(
    state: AgentToolState,
    why: SearchChoice | None,
    *,
    search_name: str = EXPORTED.name,
    params: dict[str, str | list[str] | None] | None = None,
) -> str:
    """The retry the binding raised; nothing was recorded."""
    with pytest.raises(ModelRetry) as refused:
        await choose(state, why, search_name=search_name, params=params)
    assert state.operational_spec_draft.criteria == []
    return str(refused.value)
