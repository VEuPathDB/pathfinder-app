"""The qualifier rule reads WDK's definitions, not a word: "pseudogenes" binds
plasmodb's Gene Type, whose Include Pseudogenes states it, over its neighbour
Organism, which cannot."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState, CatalogHit, CatalogRead
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.tests._support.recorded_searches import (
    client_search,
    serve_recorded,
    suite_search,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    Proposals,
    frame_ctx,
    no_count,
    no_validation,
    serve_params,
    serve_site_listing,
)

_TEXT = "all Plasmodium falciparum 3D7 genes, pseudogenes included"
_TAXON = suite_search("search_genes_by_taxon")
_GENE_TYPE = suite_search("search_genes_by_gene_type")


def _state() -> AgentToolState:
    state = AgentToolState()
    state.record_catalog_read(
        CatalogRead(
            tool_call_id="call_all_genes",
            tool="search_for_searches",
            record_type="transcript",
            query="all genes of an organism",
            hits=[
                CatalogHit(
                    name=d.url_segment,
                    display_name=d.display_name,
                    record_type="transcript",
                )
                for d in (_TAXON, _GENE_TYPE)
            ],
        )
    )
    return state


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded(monkeypatch, [_TAXON, _GENE_TYPE])
    serve_params(
        monkeypatch,
        lambda _context: format_param_info_typed(_GENE_TYPE.parameters or []),
    )
    no_validation(monkeypatch)
    no_count(monkeypatch)
    serve_site_listing(monkeypatch, [])


async def _bind(state: AgentToolState, params: Proposals) -> None:
    await set_criterion(
        frame_ctx(state),
        criterion_id="c_all_genes",
        text=_TEXT,
        search_name=_GENE_TYPE.url_segment,
        role="seed",
        params=params,
        why=SearchChoice(
            basis="parameter",
            term="Include Pseudogenes",
            reason="Include Pseudogenes keeps the pseudogenes the request names",
        ),
    )


@pytest.mark.asyncio
async def test_the_neighbour_that_cannot_state_it_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = _state()

    with pytest.raises(ModelRetry) as exc:
        await set_criterion(
            frame_ctx(state),
            criterion_id="c_all_genes",
            text=_TEXT,
            search_name=_TAXON.url_segment,
            role="seed",
        )

    assert str(exc.value) == (
        "c_all_genes: Organism has no parameter that states 'pseudogenes'. On "
        "plasmodb, Gene Type carries 'pseudogenes' (Gene type, Include "
        "Pseudogenes). Bind that search. Nothing was recorded."
    )
    assert state.open_sheets == {}


@pytest.mark.asyncio
async def test_the_search_that_states_it_is_held_to_a_value_that_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = _state()

    with pytest.raises(ModelRetry) as exc:
        await _bind(
            state,
            {
                "organism": ["Plasmodium falciparum 3D7"],
                "geneType": ["protein coding"],
                "includePseudogenes": "No",
            },
        )

    assert str(exc.value) == (
        "c_all_genes states 'pseudogenes', and Gene Type states it only through "
        "Gene type (geneType) or Include Pseudogenes (includePseudogenes), which "
        "this call leaves at its default or switched off. Set geneType to "
        "pseudogene or includePseudogenes to Yes or Pseudogenes Only. Nothing "
        "was recorded."
    )
    assert state.operational_spec_draft.criteria == []


@pytest.mark.asyncio
async def test_a_value_that_states_it_binds(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch)
    state = _state()

    await _bind(
        state,
        {
            "organism": ["Plasmodium falciparum 3D7"],
            "geneType": ["protein coding"],
            "includePseudogenes": "Yes",
        },
    )

    [criterion] = state.operational_spec_draft.criteria
    assert criterion.search_name == "GenesByGeneType"
    assert criterion.unexpressed_qualifiers == []


@pytest.mark.asyncio
async def test_a_qualifier_no_search_of_the_pass_states_is_recorded_unexpressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_recorded(monkeypatch, [_TAXON, _GENE_TYPE])
    serve_params(
        monkeypatch,
        lambda _context: format_param_info_typed(_TAXON.parameters or []),
    )
    no_validation(monkeypatch)
    no_count(monkeypatch)
    serve_site_listing(monkeypatch, [])
    state = AgentToolState()
    state.record_catalog_read(
        CatalogRead(
            tool_call_id="call_taxon",
            tool="search_for_searches",
            record_type="transcript",
            query="all genes of an organism",
            hits=[
                CatalogHit(
                    name=_TAXON.url_segment,
                    display_name=_TAXON.display_name,
                    record_type="transcript",
                )
            ],
        )
    )

    await set_criterion(
        frame_ctx(state),
        criterion_id="c_all_genes",
        text=_TEXT,
        search_name=_TAXON.url_segment,
        role="seed",
        params={"organism": ["Plasmodium falciparum 3D7"]},
        why=SearchChoice(
            basis="organism",
            term="Plasmodium falciparum 3D7",
            reason="Organism covers Plasmodium falciparum 3D7",
        ),
    )

    [criterion] = state.operational_spec_draft.criteria
    assert criterion.search_name == "GenesByTaxon"
    assert criterion.unexpressed_qualifiers == ["pseudogenes"]


_ORTHOLOGS = client_search("search_genes_by_orthologs")
_MAPS = "map the pseudogenes of that set to their orthologs in Plasmodium vivax P01"


async def _open_the_transform(state: AgentToolState) -> None:
    await set_criterion(
        frame_ctx(state),
        criterion_id="c_to_pviv",
        text=_MAPS,
        search_name=_ORTHOLOGS.url_segment,
        role="transform",
    )


def _drafted_with_the_types(monkeypatch: pytest.MonkeyPatch) -> AgentToolState:
    serve_recorded(monkeypatch, [_TAXON, _GENE_TYPE, _ORTHOLOGS])
    state = _state()
    state.frame_set_criterion(
        Criterion(
            id="c_gene_types",
            text="pseudogenes included",
            search_name=_GENE_TYPE.url_segment,
        )
    )
    return state


@pytest.mark.asyncio
async def test_a_transform_leaves_the_words_of_its_input_to_the_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _drafted_with_the_types(monkeypatch)

    await _open_the_transform(state)

    assert list(state.open_sheets) == ["c_to_pviv"]


@pytest.mark.asyncio
async def test_a_transform_with_no_input_stating_the_word_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_recorded(monkeypatch, [_TAXON, _GENE_TYPE, _ORTHOLOGS])
    state = _state()

    with pytest.raises(ModelRetry) as exc:
        await _open_the_transform(state)

    assert str(exc.value) == (
        "c_to_pviv: Transform by Orthology has no parameter that states "
        "'pseudogenes'. On plasmodb, Gene Type carries 'pseudogenes' (Gene type, "
        "Include Pseudogenes). Bind that search. Nothing was recorded."
    )


@pytest.mark.asyncio
async def test_a_filter_is_held_to_the_word_another_criterion_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _drafted_with_the_types(monkeypatch)

    with pytest.raises(ModelRetry) as exc:
        await set_criterion(
            frame_ctx(state),
            criterion_id="c_all_genes",
            text=_TEXT,
            search_name=_TAXON.url_segment,
            role="seed",
        )

    assert str(exc.value) == (
        "c_all_genes: Organism has no parameter that states 'pseudogenes'. On "
        "plasmodb, Gene Type carries 'pseudogenes' (Gene type, Include "
        "Pseudogenes). Bind that search. Nothing was recorded."
    )
