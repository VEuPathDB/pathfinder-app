"""The N1 criterion binds Short Variant Characteristics: "isolates" in a P. vivax
experiment's label outstates nothing, and only SNV Characteristics Within a
Group of Samples, whose MinPercentIsolateCalls names it, can outstate it. The
definitions are the ones plasmodb published."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
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

_VARIANTS = suite_search("search_genes_by_variant_characteristics")
_SNVS = suite_search("search_genes_by_ngs_snps")
_PVIV = suite_search("search_genes_by_rnaseq_pviv_patient_idc_percentile")
_N1 = (
    "genes whose highest minor-allele frequency is at most 5% across "
    "P. falciparum isolates"
)


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded(monkeypatch, [_VARIANTS, _SNVS, _PVIV])
    serve_params(
        monkeypatch,
        lambda _context: format_param_info_typed(_VARIANTS.parameters or []),
    )
    no_validation(monkeypatch)
    no_count(monkeypatch)
    serve_site_listing(monkeypatch, [])


def _ranked(*definitions: WDKSearch) -> AgentToolState:
    state = AgentToolState()
    state.record_catalog_read(
        CatalogRead(
            tool_call_id="call_isolates",
            tool="search_for_searches",
            record_type="transcript",
            query="genes that do not vary much between isolates",
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


async def _open(state: AgentToolState, text: str) -> None:
    await set_criterion(
        frame_ctx(state),
        criterion_id="c_conserved",
        text=text,
        search_name=_VARIANTS.url_segment,
        role="filter",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ranked", [(_PVIV,), (_PVIV, _SNVS)], ids=["pviv-only", "pviv-and-owner"]
)
async def test_the_n1_criterion_opens_the_variant_search(
    monkeypatch: pytest.MonkeyPatch, ranked: tuple[WDKSearch, ...]
) -> None:
    _serve(monkeypatch)
    state = _ranked(*ranked)

    await _open(state, _N1)

    assert list(state.open_sheets) == ["c_conserved"]


@pytest.mark.asyncio
async def test_3d7_isolates_are_refused_in_favour_of_the_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = _ranked(_PVIV, _SNVS)

    with pytest.raises(ModelRetry) as exc:
        await _open(
            state, "genes that do not vary much between Plasmodium 3D7 isolates"
        )

    assert str(exc.value) == (
        "c_conserved: Short Variant Characteristics has no parameter that states "
        "'isolates'. On plasmodb, SNV Characteristics Within a Group of Samples "
        "carries 'isolates' (Percent samples with a base call >= ). Bind that "
        "search. Nothing was recorded."
    )
    assert state.open_sheets == {}
