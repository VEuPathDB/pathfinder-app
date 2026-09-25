"""Reading another site's experiment answers its card and records what FRAME may cite."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import WDKSearch, WDKSearchResponse
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import UnknownExperimentError
from veupathdb_mcp.embeddings import SemanticIndexUnavailableError

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._catalog_elsewhere import (
    ExperimentRead,
    read_experiment,
    tree_tops,
)
from pathfinder.ai.tools.standalone._frame_rationale import sources_retrieved
from pathfinder.tests._support.experiment_cards import (
    CRYPTO_CARD,
    CRYPTO_SEARCH,
    EIMERIA_GENOME_CARD,
)
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_ORTHOLOGS = WDKSearchResponse.model_validate(
    load_recorded("search_genes_by_orthologs").json_body()
).search_data


def _serve(monkeypatch: pytest.MonkeyPatch, definition: WDKSearch) -> AsyncMock:
    """Plasmodb's gene searches hold its orthology transform, as recorded."""
    reads = AsyncMock(return_value=CRYPTO_CARD)
    monkeypatch.setattr(catalog, "read_experiment", reads)
    monkeypatch.setattr(
        catalog, "get_raw_searches", AsyncMock(return_value=[definition])
    )
    monkeypatch.setattr(
        catalog, "read_search_definition", AsyncMock(return_value=definition)
    )
    return reads


def _shown_cryptodb() -> RunContext[AgentDeps]:
    state = AgentToolState()
    state.record_elsewhere([CRYPTO_CARD], frozenset())
    return agent_run_context(agent_state=state)


@pytest.mark.asyncio
async def test_the_card_is_answered_with_its_site_and_the_orthology_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads = _serve(monkeypatch, _ORTHOLOGS)

    answer = returned(
        await read_experiment(_shown_cryptodb(), "DS_63b0de882c"), ExperimentRead
    )

    reads.assert_awaited_once_with("cryptodb", "DS_63b0de882c")
    assert answer == ExperimentRead(
        site="cryptodb",
        dataset_id="DS_63b0de882c",
        name="Transcriptome of 48 hours in vitro infection",
        organism="Cryptosporidium parvum Iowa II",
        assay="RNASeq",
        attribution="Isaza et al.",
        summary=(
            "Transcriptome (RNA-Seq) from Cryptosporidium parvum Iowa isolated from "
            "an in vitro infection of cultured HCT-8 cells."
        ),
        pmids=["26549794"],
        record_url="https://cryptodb.org/cryptodb/app/record/dataset/DS_63b0de882c",
        searches=["GenesByIntronJunctions", CRYPTO_SEARCH],
        where_they_run="These searches run on cryptodb, not on plasmodb.",
        orthology=(
            "Transform by Orthology on plasmodb reaches Haemoproteidae and "
            "Plasmodiidae; a transform to Cryptosporidium parvum Iowa II runs on "
            "the VEuPathDB portal, where one strategy holds both organisms."
        ),
    )


@pytest.mark.asyncio
async def test_the_record_and_its_publications_are_recorded_as_retrieved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _ORTHOLOGS)
    ctx = _shown_cryptodb()

    await read_experiment(ctx, "DS_63b0de882c")

    record = "https://cryptodb.org/cryptodb/app/record/dataset/DS_63b0de882c"
    assert ctx.deps.turn_markers.retrieved_sources == [record, "26549794"]
    assert sources_retrieved(ctx, "c_infection", [record, "PMID:26549794"]) == [
        record,
        "26549794",
    ]


@pytest.mark.asyncio
async def test_an_experiment_this_pass_did_not_show_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads = _serve(monkeypatch, _ORTHOLOGS)

    with pytest.raises(ModelRetry) as refused:
        await read_experiment(_shown_cryptodb(), "DS_0d220fc0c6")

    assert str(refused.value) == (
        "DS_0d220fc0c6 is not an experiment this pass showed. Read one of: "
        "DS_63b0de882c."
    )
    reads.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_pass_that_showed_none_is_told_where_they_come_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _ORTHOLOGS)

    with pytest.raises(ModelRetry) as refused:
        await read_experiment(agent_run_context(), "DS_63b0de882c")

    assert str(refused.value) == (
        "DS_63b0de882c is not an experiment this pass showed. search_for_searches "
        "shows other sites' experiments in its otherSites entry."
    )


@pytest.mark.asyncio
async def test_a_store_that_does_not_answer_records_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _ORTHOLOGS)
    monkeypatch.setattr(
        catalog,
        "read_experiment",
        AsyncMock(side_effect=SemanticIndexUnavailableError("store down")),
    )
    ctx = _shown_cryptodb()

    with pytest.raises(ModelRetry) as refused:
        await read_experiment(ctx, "DS_63b0de882c")

    assert str(refused.value) == (
        "The experiment store does not answer now, so DS_63b0de882c cannot be read. "
        "Go on with the searches on plasmodb."
    )
    assert ctx.deps.turn_markers.retrieved_sources == []


@pytest.mark.asyncio
async def test_a_card_the_site_no_longer_holds_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _ORTHOLOGS)
    monkeypatch.setattr(
        catalog,
        "read_experiment",
        AsyncMock(side_effect=UnknownExperimentError("cryptodb", "DS_63b0de882c")),
    )

    with pytest.raises(ModelRetry) as refused:
        await read_experiment(_shown_cryptodb(), "DS_63b0de882c")

    assert str(refused.value) == (
        "cryptodb no longer holds DS_63b0de882c, so it cannot be read. Go on with "
        "the searches on plasmodb."
    )


def test_a_citation_no_read_returned_names_the_reads_that_count() -> None:
    with pytest.raises(ModelRetry) as refused:
        sources_retrieved(_shown_cryptodb(), "c_infection", ["PMID:26549794"])

    assert str(refused.value) == (
        "The why of c_infection cites PMID:26549794, and no read of this turn "
        "returned it. Cite only what a research read or read_experiment returned "
        "this turn, or leave sources empty; nothing was recorded."
    )


def test_the_top_of_a_vocabulary_tree_is_read_from_the_sheet() -> None:
    assert tree_tops(_ORTHOLOGS, "organism") == ["Haemoproteidae", "Plasmodiidae"]
    assert tree_tops(_ORTHOLOGS, "isSyntenic") == []
    assert tree_tops(_ORTHOLOGS, "no_such_parameter") == []


@pytest.mark.asyncio
async def test_a_card_lists_the_first_six_searches_it_feeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _ORTHOLOGS)
    monkeypatch.setattr(
        catalog, "read_experiment", AsyncMock(return_value=EIMERIA_GENOME_CARD)
    )
    state = AgentToolState()
    state.record_elsewhere([EIMERIA_GENOME_CARD], frozenset())

    answer = returned(
        await read_experiment(agent_run_context(agent_state=state), "DS_299615a94a"),
        ExperimentRead,
    )

    assert answer.searches == [
        "GenesByInterproDomain",
        "GenesWithSignalPeptide",
        "GeneByLocusTag",
        "GenesByTransmembraneDomains",
        "GenesWithUserComments",
        "GenesByExonCount",
    ]
