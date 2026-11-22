from __future__ import annotations

import pytest
from pydantic import JsonValue
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.wdk import WDKParameter, WDKSearch
from veupathdb_mcp.catalog import FilterReads, ParamFetcher

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone import _frame_proposals, frame_spec
from strategist.ai.tools.standalone._frame_proposals import (
    CriterionCall,
    refuse_unknown_names,
)
from strategist.ai.tools.standalone._frame_stated import refuse_what_the_words_decide
from strategist.ai.tools.standalone.strategy_edits import update_leaf_params
from strategist.domain.strategy.orthology_request import OrthologyRequest
from strategist.tests._support.filter_reads import NoFilterReads
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.record_classes import list_every_search_under
from strategist.tests._support.recorded_counts import no_measurements
from strategist.tests._support.recorded_searches import (
    no_count,
    serve_recorded,
    serve_stated_reads,
    suite_search,
)
from strategist.tests.unit.ai.tools._apply_operations_stubs import (
    context_and_commit,
    graph_with,
)
from strategist.tests.unit.ai.tools.conftest import serve_no_other_sites
from strategist.tests.unit.ai.tools.test_frame_spec import (
    bind,
    no_validation,
    serve_site_listing,
)

_TAXON = suite_search("search_genes_by_taxon")
_VECTOR_ORTHOLOGS = suite_search("search_genes_by_orthologs_vectorbase")
_PF = "Plasmodium falciparum 3D7"


def _serve(monkeypatch: pytest.MonkeyPatch, definition: WDKSearch) -> None:
    list_every_search_under(monkeypatch, "transcript")
    serve_recorded(monkeypatch, [definition])

    def _fetch_at(_site: str, _record_type: str, _search: str) -> ParamFetcher:
        async def fetch_at(_context: dict[str, str]) -> list[WDKParameter]:
            return list(definition.parameters or [])

        return fetch_at

    def _reads(_site: str, _record_type: str, _search: str) -> FilterReads:
        return NoFilterReads()

    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)
    monkeypatch.setattr(_frame_proposals, "WDKFilterReads", _reads)
    no_validation(monkeypatch)
    no_count(monkeypatch)
    no_measurements(monkeypatch)
    serve_site_listing(monkeypatch, [])
    serve_no_other_sites(monkeypatch)


async def _framed(monkeypatch: pytest.MonkeyPatch, organism: str) -> str:
    _serve(monkeypatch, _TAXON)
    with pytest.raises(ModelRetry) as refused:
        await bind(
            AgentToolState(),
            _TAXON.url_segment,
            {"organism": [organism]},
            text=f"genes of {organism}",
        )
    return refused.value.message


async def _edited(monkeypatch: pytest.MonkeyPatch, organism: str) -> str:
    serve_stated_reads(monkeypatch, [_TAXON])
    ctx, _ = context_and_commit(
        graph_with(StrategyStepNode(id="step_t", search_name="GenesByTaxon")), []
    )
    with pytest.raises(ModelRetry) as refused:
        await update_leaf_params(ctx, "step_t", {"organism": [organism]})
    return refused.value.message


def _candidates(refusal: str) -> str:
    return refusal.split("Candidates: ", 1)[1].rsplit(". Nothing was", 1)[0]


async def test_frame_and_an_edit_refuse_a_spelling_with_the_same_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    framed = await _framed(monkeypatch, "P. falciparum 3D7")
    edited = await _edited(monkeypatch, "P. falciparum 3D7")

    assert framed.startswith("organism has no entry 'P. falciparum 3D7'.")
    assert edited.startswith("GenesByTaxon: organism has no entry 'P. falciparum")
    assert _candidates(framed) == _candidates(edited)
    assert _candidates(framed).startswith(_PF)


async def test_a_strain_code_is_refused_with_the_entry_it_abbreviates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refusal = await _framed(monkeypatch, "Pf3D7")

    assert _PF in _candidates(refusal)
    assert "get_parameter_options" not in refusal
    assert "Trypanosoma" not in refusal
    assert refusal.endswith("Nothing was recorded.")


def test_a_misspelt_parameter_name_is_refused_with_the_nearest_name() -> None:
    call = CriterionCall(
        criterion_id="c_taxon",
        search_name="GenesByTaxon",
        text="genes of P. falciparum",
        params={"organsim": [_PF]},
    )

    with pytest.raises(ModelRetry) as refused:
        refuse_unknown_names(call, sheet_of(_TAXON.parameters or []))

    assert "Nearest: ['organism']" in refused.value.message


def test_a_transform_to_an_organism_the_vocabulary_lacks_shows_the_ranked_entries() -> (
    None
):
    params: dict[str, JsonValue] = {}
    call = CriterionCall(
        criterion_id="c_to_pf",
        search_name=_VECTOR_ORTHOLOGS.url_segment,
        text="their orthologs in P. falciparum",
        params=params,
    ).with_values(
        {
            "organism": MultiPickValue(values=["Aedes aegypti LVP_AGWG"]),
            "isSyntenic": SinglePickValue(value="no"),
        }
    )
    infos = sheet_of(_VECTOR_ORTHOLOGS.parameters or [])
    state = AgentToolState(
        orthology_request=OrthologyRequest(shape="transform", target="P. falciparum")
    )

    with pytest.raises(ModelRetry) as refused:
        refuse_what_the_words_decide(_VECTOR_ORTHOLOGS, call, infos, state)

    assert (
        "Nearest entries: ['Dermacentor silvarum', 'Culex quinquefasciatus', "
        "'Calliphoridae', 'Culicidae', 'Aedes albopictus']."
    ) in refused.value.message
