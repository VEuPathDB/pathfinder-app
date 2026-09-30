"""Only the search whose parameter names make a word a qualifier can outstate
the bound search on it; a word in another search's option label cannot. The
definitions and names are the ones plasmodb published: "stage" is named by
Phenotypes in Rodent Malaria's RodMalStage, and the Gomez-Diaz percentile
search carries it only in its Experiment and Samples labels."""

from __future__ import annotations

import pytest
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState, CatalogHit, CatalogRead
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.tests._support.recorded_searches import (
    no_count,
    serve_recorded,
    suite_search,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    no_validation,
    serve_params,
    serve_site_listing,
)

_SIGNAL = suite_search("search_genes_with_signal_peptide")
_BLOOD = suite_search("search_genes_by_rnaseq_gomez_diaz_percentile")
_OWNER = "GenesByRodentMalariaPhenotype"


def _state() -> AgentToolState:
    state = AgentToolState(
        request_messages=["genes with a predicted signal peptide in the blood stage"]
    )
    state.record_catalog_read(
        CatalogRead(
            tool_call_id="call_ranked",
            tool="search_for_searches",
            record_type="transcript",
            query="signal peptide in the blood stage",
            hits=[
                CatalogHit(
                    name=d.url_segment,
                    display_name=d.display_name,
                    record_type="transcript",
                    similarity=0.6,
                )
                for d in (_SIGNAL, _BLOOD)
            ],
        )
    )
    state.frame_set_criterion(
        Criterion(id="c_phenotype", text="a rodent phenotype", search_name=_OWNER)
    )
    return state


@pytest.mark.asyncio
async def test_a_label_of_another_search_does_not_outstate_the_bound_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_recorded(monkeypatch, [_SIGNAL, _BLOOD])
    serve_params(
        monkeypatch,
        lambda _context: format_param_info_typed(_SIGNAL.parameters or []),
    )
    no_validation(monkeypatch)
    no_count(monkeypatch)
    serve_site_listing(monkeypatch, [])
    state = _state()

    await set_criterion(
        frame_ctx(state),
        criterion_id="c_signal",
        text="genes with a predicted signal peptide in the blood stage",
        search_name=_SIGNAL.url_segment,
        role="seed",
        params={"organism": ["Plasmodium falciparum 3D7"], "signalp_version": None},
        why=SearchChoice(
            basis="organism",
            term="Plasmodium falciparum 3D7",
            reason="Predicted Signal Peptide covers Plasmodium falciparum 3D7",
        ),
    )

    [criterion] = [
        c for c in state.operational_spec_draft.criteria if c.id == "c_signal"
    ]
    assert criterion.search_name == "GenesWithSignalPeptide"
    assert criterion.unexpressed_qualifiers == ["stage"]
