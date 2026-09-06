"""``get_search_overview`` and ``get_parameter_options``: what a read answers,
what it registers on the gate, and what it refuses."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters.wdk_vocab import VocabOption
from veupathdb.errors import WDKError
from veupathdb.wdk.wdk_parameters import WDKStringParam
from veupathdb_mcp.catalog import search_inspection, searches
from veupathdb_mcp.catalog.param_formatting import (
    ParameterInfo,
    ParameterNotOnSearch,
)

from pathfinder.ai.tools.standalone import catalog_discovery
from pathfinder.ai.tools.standalone.catalog_discovery import AlreadyReadNotice
from pathfinder.tests.unit.ai.tools.conftest import (
    agent_state_ctx,
    patch_search_details,
    summary_of,
    wdk_param,
)

_GOAL = "kinase genes expressed in the schizont stage"


def _params(names: list[str]) -> list[Any]:
    return [wdk_param(name) for name in names]


def _pin_formatter(monkeypatch: pytest.MonkeyPatch) -> Any:
    info = MagicMock(kind="parameter_info")
    monkeypatch.setattr(
        search_inspection, "format_typed_param", lambda *_a, **_kw: info
    )
    return info


def _param_info(**overrides: Any) -> ParameterInfo:
    base: dict[str, Any] = {
        "name": "p",
        "display_name": "P",
        "type": "string",
        "required": True,
        "is_visible": True,
        "help": "",
        "value_format": "",
    }
    base.update(overrides)
    return ParameterInfo.model_validate(base)


def _overview_client(monkeypatch: pytest.MonkeyPatch) -> Any:
    """A search whose overview is formatted by a stub, so only the tool runs."""

    async def _resolve(*_a: Any, **_k: Any) -> str:
        return "transcript"

    monkeypatch.setattr(search_inspection, "resolve_search_record_type", _resolve)
    search_data = MagicMock()
    search_data.url_segment = "GenesByGoTerm"
    search_data.display_name = "Genes by GO Term"
    search_data.description = "Find genes by GO term"
    search_data.summary = "summary"
    search_data.parameters = [
        WDKStringParam(name="go_term", is_visible=True, allow_empty_value=False),
        WDKStringParam(name="taxon", is_visible=True, allow_empty_value=False),
    ]
    details = MagicMock()
    details.search_data = search_data
    client = MagicMock()
    client.get_search_details = AsyncMock(return_value=details)
    monkeypatch.setattr(searches, "get_wdk_client", lambda _site: client)
    return client


class TestTheSearchOverviewRead:
    async def test_the_first_read_registers_the_second_is_a_notice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _overview_client(monkeypatch)
        monkeypatch.setattr(
            search_inspection, "format_search_overview", lambda **_kw: MagicMock()
        )
        ctx = agent_state_ctx()

        first = (
            await catalog_discovery.get_search_overview(
                ctx, search_name="GenesByGoTerm"
            )
        ).return_value
        assert not isinstance(first, AlreadyReadNotice)
        assert ctx.deps.agent_state.get_overview("GenesByGoTerm") is not None
        assert client.get_search_details.await_count == 1

        second = (
            await catalog_discovery.get_search_overview(
                ctx, search_name="GenesByGoTerm"
            )
        ).return_value
        assert isinstance(second, AlreadyReadNotice)
        assert second.search_name == "GenesByGoTerm"
        assert client.get_search_details.await_count == 1

    async def test_the_sheet_is_ranked_on_the_goal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _overview_client(monkeypatch)
        captured: dict[str, str] = {}

        def _overview(*, query: str, **_kw: Any) -> Any:
            captured["query"] = query
            return MagicMock()

        monkeypatch.setattr(search_inspection, "format_search_overview", _overview)
        ctx = agent_state_ctx()
        ctx.deps.agent_state.operational_spec_draft.goal = _GOAL

        await catalog_discovery.get_search_overview(ctx, search_name="GenesByGoTerm")

        assert captured["query"] == _GOAL

    async def test_a_404_raises_a_model_retry_with_a_did_you_mean(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An invented name must come back as a correction, not a dead turn."""

        async def _resolve(*_a: Any, **_k: Any) -> str:
            return "transcript"

        monkeypatch.setattr(search_inspection, "resolve_search_record_type", _resolve)
        client = MagicMock()
        client.get_search_details = AsyncMock(
            side_effect=WDKError(
                "Resource 'search: GenesByText_Search' does not exist.", status=404
            )
        )
        monkeypatch.setattr(searches, "get_wdk_client", lambda _s: client)

        async def _valid(_site: str, _rt: str) -> list[Any]:
            return [
                MagicMock(url_segment="GenesByText"),
                MagicMock(url_segment="GenesByGoTerm"),
            ]

        monkeypatch.setattr(search_inspection, "get_raw_searches", _valid)
        ctx = agent_state_ctx(site_id="vectorbase")

        with pytest.raises(ModelRetry) as excinfo:
            await catalog_discovery.get_search_overview(
                ctx, search_name="GenesByText_Search"
            )

        msg = str(excinfo.value)
        assert "GenesByText" in msg
        assert "GenesByText_Search" in msg
        assert ctx.deps.agent_state.get_overview("GenesByText_Search") is None

    async def test_a_non_404_wdk_error_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _resolve(*_a: Any, **_k: Any) -> str:
            return "transcript"

        monkeypatch.setattr(search_inspection, "resolve_search_record_type", _resolve)
        client = MagicMock()
        client.get_search_details = AsyncMock(
            side_effect=WDKError("upstream 502", status=502)
        )
        monkeypatch.setattr(searches, "get_wdk_client", lambda _s: client)

        with pytest.raises(WDKError):
            await catalog_discovery.get_search_overview(
                agent_state_ctx(site_id="vectorbase"), search_name="GenesByText"
            )


class TestTheParameterRead:
    async def test_a_known_parameter_returns_the_formatted_info(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        patch_search_details(
            monkeypatch,
            parameters=_params(["min_pct_idents", "min_overlap_size"]),
        )
        info = _pin_formatter(monkeypatch)

        result = (
            await catalog_discovery.get_parameter_options(
                agent_state_ctx(),
                search_name="GenesByESTOverlap",
                parameter_id="min_pct_idents",
            )
        ).return_value

        assert result is info

    async def test_an_unknown_id_returns_the_close_match_and_the_valid_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        patch_search_details(
            monkeypatch,
            parameters=_params(
                ["min_pct_idents", "min_overlap_size", "datasets", "expansion_factor"]
            ),
        )

        result = (
            await catalog_discovery.get_parameter_options(
                agent_state_ctx(),
                search_name="GenesByESTOverlap",
                parameter_id="minOverlap",
            )
        ).return_value

        assert isinstance(result, ParameterNotOnSearch)
        assert result.requested_parameter_id == "minOverlap"
        assert result.search_name == "GenesByESTOverlap"
        assert "min_overlap_size" in result.suggestions
        assert set(result.valid_parameter_ids) == {
            "min_pct_idents",
            "min_overlap_size",
            "datasets",
            "expansion_factor",
        }
        assert "minOverlap" in result.message
        assert "GenesByESTOverlap" in result.message

    async def test_no_close_match_still_lists_all_valid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        patch_search_details(monkeypatch, parameters=_params(["taxon", "go_term"]))

        result = (
            await catalog_discovery.get_parameter_options(
                agent_state_ctx(),
                search_name="GenesByGoTerm",
                parameter_id="completely_unrelated_xyz",
            )
        ).return_value

        assert isinstance(result, ParameterNotOnSearch)
        assert result.requested_parameter_id == "completely_unrelated_xyz"
        assert set(result.valid_parameter_ids) == {"taxon", "go_term"}
        assert "completely_unrelated_xyz" in result.message
        assert "taxon" in result.message
        assert "go_term" in result.message

    async def test_a_second_identical_read_returns_an_already_read_notice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        patch_search_details(monkeypatch, parameters=_params(["go_term", "taxon"]))
        info = _pin_formatter(monkeypatch)
        ctx = agent_state_ctx()

        first = (
            await catalog_discovery.get_parameter_options(
                ctx, search_name="GenesByGoTerm", parameter_id="go_term"
            )
        ).return_value
        assert first is info

        second = (
            await catalog_discovery.get_parameter_options(
                ctx, search_name="GenesByGoTerm", parameter_id="go_term"
            )
        ).return_value
        assert isinstance(second, AlreadyReadNotice)
        assert second.search_name == "GenesByGoTerm"
        assert second.parameter_id == "go_term"

    async def test_a_failed_read_is_not_marked_so_a_retry_works(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        patch_search_details(monkeypatch, parameters=_params(["go_term", "taxon"]))
        info = _pin_formatter(monkeypatch)
        ctx = agent_state_ctx()

        wrong = (
            await catalog_discovery.get_parameter_options(
                ctx, search_name="GenesByGoTerm", parameter_id="goTerm"
            )
        ).return_value
        assert isinstance(wrong, ParameterNotOnSearch)

        fixed = (
            await catalog_discovery.get_parameter_options(
                ctx, search_name="GenesByGoTerm", parameter_id="go_term"
            )
        ).return_value
        assert fixed is info


class TestTheOptionCountSummary:
    """The trace line counts what the model can actually pick from."""

    async def _read_summary(
        self, monkeypatch: pytest.MonkeyPatch, info: ParameterInfo
    ) -> Any:
        monkeypatch.setattr(
            catalog_discovery,
            "read_parameter_options",
            AsyncMock(return_value=info),
        )
        returned = await catalog_discovery.get_parameter_options(
            agent_state_ctx(), search_name="GenesByMassSpec", parameter_id=info.name
        )
        return summary_of(returned).data

    async def test_a_tree_vocabulary_counts_its_leaves(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        info = _param_info(
            name="ms_assay",
            type="multi-pick-vocabulary",
            allowed_values=None,
            allowed_values_tree="Anopheles\n  sample_a\n  sample_b",
            vocab_leaves=[
                VocabOption(value="sample_a", display="Sample A"),
                VocabOption(value="sample_b", display="Sample B"),
            ],
        )
        data = await self._read_summary(monkeypatch, info)

        assert data["summary"] == "ms_assay: 2 options"
        assert data["status"] == "ok"

    async def test_a_free_form_parameter_reports_no_vocabulary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data = await self._read_summary(
            monkeypatch, _param_info(name="snp_density_upper", type="number")
        )

        assert data["summary"] == "snp_density_upper: free-form number, no vocabulary"
        assert data["status"] == "ok"

    async def test_an_empty_pick_vocabulary_stays_flagged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data = await self._read_summary(
            monkeypatch, _param_info(name="organism", type="single-pick-vocabulary")
        )

        assert data["summary"] == "organism: 0 options"
        assert data["status"] == "empty"
