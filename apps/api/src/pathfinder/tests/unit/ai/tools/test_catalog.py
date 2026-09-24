"""The catalog listing tools record every search they show the model."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock

import pytest
from assistant_core.platform.types import JSONObject
from pydantic_ai import RunContext
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import RecordTypeInfo, SearchMatch, searches

from pathfinder.ai.agents.state import (
    AgentToolState,
    CatalogHit,
    CatalogRead,
    SearchOverview,
)
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.catalog import (
    get_record_types,
    list_searches,
    list_transforms,
    search_for_searches,
)
from pathfinder.ai.tools.toolsets.frame import _frame_enum_overrides
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context


def _ctx(state: AgentToolState) -> RunContext[AgentDeps]:
    return agent_run_context(agent_state=state)


def _inspected(name: str) -> SearchOverview:
    return SearchOverview(
        search_name=name,
        display_name=name,
        record_type="transcript",
        description="already inspected",
        parameter_names=["taxon"],
        required_params=["taxon"],
    )


def _match(
    name: str,
    display_name: str,
    relevance: float,
    similarity: float | None = 0.62,
) -> SearchMatch:
    return SearchMatch(
        name=name,
        display_name=display_name,
        description=f"Find genes by {display_name}",
        record_type="transcript",
        category="general",
        returns="transcript",
        relevance=relevance,
        semantic_similarity=similarity,
    )


def _serve(monkeypatch: pytest.MonkeyPatch, name: str, value: object) -> AsyncMock:
    """Answer a catalog read the tools reach through the package."""
    mock = AsyncMock(return_value=value)
    monkeypatch.setattr(catalog, name, mock)
    return mock


def _serve_listing(
    monkeypatch: pytest.MonkeyPatch, name: str, value: object
) -> AsyncMock:
    """Answer a listing the payload builders reach through the searches module."""
    mock = AsyncMock(return_value=value)
    monkeypatch.setattr(searches, name, mock)
    return mock


class TestGetRecordTypes:
    async def test_the_site_record_types_reach_the_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock = _serve(
            monkeypatch,
            "get_record_types",
            [
                RecordTypeInfo(
                    name="transcript",
                    display_name="Genes",
                    description="Gene/transcript records",
                ),
                RecordTypeInfo(
                    name="isolate",
                    display_name="Isolates",
                    description="Population isolate records",
                ),
            ],
        )

        result = returned(
            await get_record_types(_ctx(AgentToolState())), list[dict[str, str]]
        )

        assert [row["name"] for row in result] == ["transcript", "isolate"]
        assert [row["displayName"] for row in result] == ["Genes", "Isolates"]
        assert result[0]["description"] == "Gene/transcript records"
        mock.assert_awaited_once_with("plasmodb")


class TestSearchForSearches:
    async def test_it_records_every_name_it_returns(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(
            monkeypatch,
            "search_for_searches",
            [
                _match("GenesByTaxon", "Genes by Taxon", 0.85),
                _match("GenesByGoTerm", "Genes by GO Term", 0.5),
            ],
        )
        state = AgentToolState()
        state.register_search("GenesByGoTerm", _inspected("GenesByGoTerm"))

        result = returned(
            await search_for_searches(
                _ctx(state), query="gametocyte RNA-Seq differential expression"
            ),
            list[JSONObject],
        )

        assert [row.get("name") for row in result] == [
            "GenesByTaxon",
            "GenesByGoTerm",
            "GenesByText",
        ]
        assert [hit.name for hit in state.catalog_reads[-1].hits] == [
            "GenesByTaxon",
            "GenesByGoTerm",
            "GenesByText",
        ]

    async def test_the_universal_search_is_appended_to_the_matches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(
            monkeypatch,
            "search_for_searches",
            [_match("GenesByTaxon", "Genes by Taxon", 0.85)],
        )
        state = AgentToolState()

        result = returned(
            await search_for_searches(
                _ctx(state),
                query="find genes by organism taxonomy plasmodium falciparum",
            ),
            list[JSONObject],
        )

        taxon = next(row for row in result if row["name"] == "GenesByTaxon")
        assert taxon["displayName"] == "Genes by Taxon"
        assert taxon["relevance"] == 0.85
        assert taxon["recordType"] == "transcript"
        # The appended row is the library's, so it carries a ranked match's shape.
        universal = next(row for row in result if row["name"] == "GenesByText")
        assert universal["displayName"] == "Gene Text Search"
        assert universal["recordType"] == "transcript"
        assert universal["returns"] == "transcript"

    async def test_an_inspected_search_is_neither_hidden_nor_annotated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(
            monkeypatch,
            "search_for_searches",
            [
                _match("GenesByTaxon", "Genes by Taxon", 0.85),
                _match("GenesByGoTerm", "Genes by GO Term", 0.8),
            ],
        )
        state = AgentToolState()
        state.register_search("GenesByTaxon", _inspected("GenesByTaxon"))

        result = returned(
            await search_for_searches(
                _ctx(state),
                query="find genes by organism taxonomy or go term plasmodium",
            ),
            list[JSONObject],
        )

        names = [str(row.get("name")) for row in result]
        assert "GenesByTaxon" in names
        assert "GenesByGoTerm" in names
        assert [row for row in result if "note" in row] == []

    async def test_a_vague_query_is_refused(self) -> None:
        result = returned(
            await search_for_searches(_ctx(AgentToolState()), query="genes"),
            list[JSONObject],
        )

        assert len(result) == 1
        assert result[0]["error"] == "query_too_vague"


_GPI = "genes with a predicted GPI anchor attachment signal"
_FAINT = f"No search on plasmodb states '{_GPI}' closely; the nearest are listed."
_UNSCORED = (
    "The semantic index scored none of these results; the ranking is by keyword only."
)
_NOTHING = (
    f"No search on plasmodb matched '{_GPI}'; only the searches every site "
    "offers are listed."
)


class TestAFaintMatchIsReported:
    async def _ranked(
        self, monkeypatch: pytest.MonkeyPatch, matches: list[SearchMatch]
    ) -> list[JSONObject]:
        _serve(monkeypatch, "search_for_searches", matches)
        return returned(
            await search_for_searches(_ctx(AgentToolState()), query=_GPI),
            list[JSONObject],
        )

    async def test_a_best_hit_below_the_floor_is_reported_first(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = await self._ranked(
            monkeypatch,
            [
                _match("GenesByExportPrediction", "Exported Protein", 1.0, 0.31),
                _match("GenesBySignalPeptide", "Signal Peptide", 0.9, 0.29),
            ],
        )

        assert result[0] == {"note": _FAINT}
        assert [row.get("name") for row in result[1:3]] == [
            "GenesByExportPrediction",
            "GenesBySignalPeptide",
        ]

    async def test_an_unscored_hit_does_not_count_against_a_close_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = await self._ranked(
            monkeypatch,
            [
                _match("GenesByText", "Gene Text Search", 1.0, None),
                _match("GenesByGPIAnchor", "GPI Anchor", 0.8, 0.58),
            ],
        )

        assert [row["name"] for row in result] == ["GenesByText", "GenesByGPIAnchor"]

    async def test_a_ranking_the_index_scored_nowhere_says_it_is_keyword_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = await self._ranked(
            monkeypatch,
            [
                _match("GenesByExportPrediction", "Exported Protein", 1.0, None),
                _match("GenesBySignalPeptide", "Signal Peptide", 0.9, None),
            ],
        )

        assert result[0] == {"note": _UNSCORED}
        assert [row.get("name") for row in result[1:3]] == [
            "GenesByExportPrediction",
            "GenesBySignalPeptide",
        ]

    async def test_a_query_that_matches_nothing_is_reported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = await self._ranked(monkeypatch, [])

        assert result[0] == {"note": _NOTHING}
        assert [row.get("name") for row in result[1:]] == ["GenesByText"]

    async def test_a_close_best_hit_carries_no_note(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = await self._ranked(
            monkeypatch,
            [
                _match("GenesByGPIAnchor", "GPI Anchor", 1.0, 0.58),
                _match("GenesByExportPrediction", "Exported Protein", 0.4, 0.2),
            ],
        )

        assert [row for row in result if "note" in row] == []

    def test_the_model_is_told_which_score_is_absolute(self) -> None:
        doc = " ".join((inspect.getdoc(search_for_searches) or "").split())

        assert "relevance`` is relative to the best hit" in doc
        assert "``semanticSimilarity`` is the absolute cosine" in doc


class TestListSearches:
    async def test_it_records_the_visible_names(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve_listing(
            monkeypatch,
            "list_searches",
            [
                {"name": "GenesByTaxon", "displayName": "Genes by Taxon"},
                {"name": "GenesByGoTerm", "displayName": "Genes by GO Term"},
            ],
        )
        state = AgentToolState()
        state.register_search("GenesByGoTerm", _inspected("GenesByGoTerm"))

        result = returned(await list_searches(_ctx(state)), list[str])

        assert result == ["GenesByTaxon", "GenesByGoTerm"]
        assert state.catalog_reads == [
            CatalogRead(
                tool_call_id="call_1",
                tool="list_searches",
                record_type="transcript",
                hits=[
                    CatalogHit(
                        name="GenesByTaxon",
                        display_name="Genes by Taxon",
                        record_type="transcript",
                    ),
                    CatalogHit(
                        name="GenesByGoTerm",
                        display_name="Genes by GO Term",
                        record_type="transcript",
                    ),
                ],
            )
        ]

    async def test_one_record_type_narrows_the_listing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock = _serve_listing(
            monkeypatch,
            "list_searches",
            [
                {"name": "GenesByTaxon", "displayName": "Genes by Taxon"},
                {"name": "GenesByLocation", "displayName": "Genes by Genomic Location"},
                {"name": "GenesByText", "displayName": "Gene Text Search"},
            ],
        )

        result = returned(
            await list_searches(_ctx(AgentToolState()), record_type="transcript"),
            list[str],
        )

        assert result == ["GenesByTaxon", "GenesByLocation", "GenesByText"]
        mock.assert_awaited_once_with("plasmodb", "transcript")

    async def test_an_inspected_search_stays_in_the_listing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve_listing(
            monkeypatch,
            "list_searches",
            [
                {"name": "GenesByTaxon", "displayName": "Genes by Taxon"},
                {"name": "GenesByText", "displayName": "Gene Text Search"},
            ],
        )
        state = AgentToolState()
        state.register_search("GenesByTaxon", _inspected("GenesByTaxon"))

        result = returned(
            await list_searches(_ctx(state), record_type="transcript"), list[str]
        )

        assert result == ["GenesByTaxon", "GenesByText"]


class TestListTransforms:
    async def test_it_records_the_transform_names(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve_listing(
            monkeypatch,
            "list_transforms",
            [
                {
                    "name": "GenesByOrthologs",
                    "displayName": "Transform to Orthologs",
                    "description": "Orthologs of the input genes.",
                }
            ],
        )
        state = AgentToolState()

        result = returned(await list_transforms(_ctx(state)), list[JSONObject])

        assert [row["name"] for row in result] == ["GenesByOrthologs"]
        assert state.catalog_reads == [
            CatalogRead(
                tool_call_id="call_1",
                tool="list_transforms",
                record_type="transcript",
                hits=[
                    CatalogHit(
                        name="GenesByOrthologs",
                        display_name="Transform to Orthologs",
                        description="Orthologs of the input genes.",
                        record_type="transcript",
                    )
                ],
            )
        ]

    async def test_a_listed_transform_passes_the_search_name_guard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A transform the model was shown can be inspected and bound."""
        _serve_listing(
            monkeypatch,
            "list_transforms",
            [
                {
                    "name": "GenesByOrthologs",
                    "displayName": "Transform to Orthologs",
                    "description": "Orthologs of the input genes.",
                }
            ],
        )
        state = AgentToolState()

        await list_transforms(_ctx(state))

        overrides = _frame_enum_overrides(_ctx(state))
        assert "GenesByOrthologs" in overrides[("get_search_overview", "search_name")]
