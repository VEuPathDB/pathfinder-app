"""The catalog listing tools record every name they show the model."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import RecordTypeInfo, SearchMatch, searches

from pathfinder.ai.agents.state import AgentToolState, SearchOverview
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools import standalone
from pathfinder.domain.strategy.session import StrategySession


def _ctx(state: AgentToolState) -> Any:
    ctx = MagicMock()
    ctx.tool_call_id = "call_1"
    ctx.deps = AgentDeps(
        site_id="plasmodb",
        strategy_session=StrategySession(site_id="plasmodb"),
        agent_state=state,
    )
    return ctx


def _inspected(name: str) -> SearchOverview:
    return SearchOverview(
        search_name=name,
        display_name=name,
        record_type="transcript",
        description="already inspected",
        parameter_names=["taxon"],
        required_params=["taxon"],
    )


def _match(name: str, display_name: str, relevance: float) -> SearchMatch:
    return SearchMatch(
        name=name,
        display_name=display_name,
        description=f"Find genes by {display_name}",
        record_type="transcript",
        category="general",
        returns="transcript",
        relevance=relevance,
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

        result = (
            await standalone.catalog.get_record_types(_ctx(AgentToolState()))
        ).return_value

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

        result = (
            await standalone.catalog.search_for_searches(
                _ctx(state), query="gametocyte RNA-Seq differential expression"
            )
        ).return_value

        assert [row.get("name") for row in result] == [
            "GenesByTaxon",
            "GenesByGoTerm",
            "GenesByText",
        ]
        assert state.catalog_search_names == {
            "GenesByTaxon",
            "GenesByGoTerm",
            "GenesByText",
        }

    async def test_the_universal_search_is_appended_to_the_matches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(
            monkeypatch,
            "search_for_searches",
            [_match("GenesByTaxon", "Genes by Taxon", 0.85)],
        )
        state = AgentToolState()

        result = (
            await standalone.catalog.search_for_searches(
                _ctx(state),
                query="find genes by organism taxonomy plasmodium falciparum",
            )
        ).return_value

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

        result = (
            await standalone.catalog.search_for_searches(
                _ctx(state),
                query="find genes by organism taxonomy or go term plasmodium",
            )
        ).return_value

        names = [str(row.get("name")) for row in result]
        assert "GenesByTaxon" in names
        assert "GenesByGoTerm" in names
        assert [row for row in result if "note" in row] == []

    async def test_a_vague_query_is_refused(self) -> None:
        result = (
            await standalone.catalog.search_for_searches(
                _ctx(AgentToolState()), query="genes"
            )
        ).return_value

        assert len(result) == 1
        assert result[0]["error"] == "query_too_vague"


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

        result = (await standalone.catalog.list_searches(_ctx(state))).return_value

        assert result == ["GenesByTaxon", "GenesByGoTerm"]
        assert state.catalog_search_names == {"GenesByTaxon", "GenesByGoTerm"}

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

        result = (
            await standalone.catalog.list_searches(
                _ctx(AgentToolState()), record_type="transcript"
            )
        ).return_value

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

        result = (
            await standalone.catalog.list_searches(
                _ctx(state), record_type="transcript"
            )
        ).return_value

        assert result == ["GenesByTaxon", "GenesByText"]
