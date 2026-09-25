"""A word is a qualifier only when exactly one search of the record type names
a parameter by it and the pass read that search.

"from" is named only by Telomere Proximity's distanceFromTelomere, which the
pass never read, and "plasmodium" names no parameter at all, so neither is held
to the search that happens to carry it in a label. The definitions are the ones
plasmodb published.
"""

from __future__ import annotations

import pytest
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState, CatalogHit, CatalogRead
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
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
_TEXT_SEARCH = suite_search("search_genes_by_text")
_BLOOD = suite_search("search_genes_by_rnaseq_gomez_diaz_percentile")
_PATHWAY = suite_search("search_genes_by_metabolic_pathway_hagai")


def _serve(monkeypatch: pytest.MonkeyPatch, *definitions: WDKSearch) -> None:
    serve_recorded(monkeypatch, list(definitions))
    serve_params(
        monkeypatch,
        lambda _context: format_param_info_typed(definitions[0].parameters or []),
    )
    no_validation(monkeypatch)
    no_count(monkeypatch)
    serve_site_listing(monkeypatch, [])


def _ranked(*definitions: WDKSearch) -> AgentToolState:
    state = AgentToolState()
    state.record_catalog_read(
        CatalogRead(
            tool_call_id="call_ranked",
            tool="search_for_searches",
            record_type="transcript",
            query="the criterion",
            hits=[
                CatalogHit(
                    name=d.url_segment,
                    display_name=d.display_name,
                    record_type="transcript",
                    similarity=0.6,
                )
                for d in definitions
            ],
        )
    )
    return state


async def _open(state: AgentToolState, search: WDKSearch, text: str) -> None:
    await set_criterion(
        frame_ctx(state),
        criterion_id="c_measured",
        text=text,
        search_name=search.url_segment,
        role="seed",
    )


@pytest.mark.asyncio
async def test_from_is_not_held_to_the_text_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _SIGNAL, _TEXT_SEARCH)
    state = _ranked(_SIGNAL, _TEXT_SEARCH)

    await _open(
        state,
        _SIGNAL,
        "genes from Plasmodium falciparum 3D7 with a predicted signal peptide",
    )

    assert list(state.open_sheets) == ["c_measured"]


@pytest.mark.asyncio
async def test_plasmodium_is_not_held_to_the_pathway_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _BLOOD, _PATHWAY)
    state = _ranked(_BLOOD, _PATHWAY)

    await _open(
        state,
        _BLOOD,
        "Plasmodium falciparum 3D7 genes expressed in asexual blood stages",
    )

    assert list(state.open_sheets) == ["c_measured"]
