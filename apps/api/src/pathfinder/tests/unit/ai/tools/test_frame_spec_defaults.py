"""A value the search defaulted is reported, not just applied."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai import RunContext
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import NumberValue, SinglePickValue
from veupathdb.domain.strategy import StepValidation
from veupathdb.wdk import WDKSearch, WDKSearchResponse
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParamFetcher,
    Provenance,
    ResolvedParams,
    ValidatedParams,
    searches,
)

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone import frame_spec
from pathfinder.ai.tools.standalone.frame_spec import SetCriterionResult
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context
from pathfinder.tests.unit.ai.tools.test_frame_spec import no_count


def _transcript_session() -> StrategySession:
    """A session holding one transcript graph, which every criterion binds on."""
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="g", site_id="plasmodb")
    graph.record_type = "transcript"
    session.add_graph(graph)
    return session


def _ctx(state: AgentToolState) -> RunContext[AgentDeps]:
    return agent_run_context(agent_state=state, strategy_session=_transcript_session())


def _resolved() -> ResolvedParams:
    return ResolvedParams(
        params={
            "organism": SinglePickValue(value="Plasmodium falciparum 3D7"),
            "min_expression_percentile": NumberValue(value=80),
        },
        provenance={
            "organism": Provenance.STATED,
            "min_expression_percentile": Provenance.DEFAULTED,
        },
    )


async def _bind(
    monkeypatch: pytest.MonkeyPatch, state: AgentToolState
) -> SetCriterionResult:
    async def _resolve(**_kw: object) -> ResolvedParams:
        return _resolved()

    async def _validate(_ctx: object, **_kw: object) -> ValidatedParams:
        return ValidatedParams()

    def _fetch_at(*_args: object) -> ParamFetcher:
        async def fetch_at(_context: dict[str, str]) -> list[ParameterInfo]:
            return []

        return fetch_at

    async def _details(
        record_type: str, name: str, *, expand_params: bool = True
    ) -> WDKSearchResponse:
        return WDKSearchResponse(
            search_data=WDKSearch(url_segment=name),
            validation=StepValidation(level="NONE", is_valid=False),
        )

    async def _catalog_details(
        ctx: SearchContext, **_kw: object
    ) -> tuple[WDKSearchResponse, str]:
        return (
            WDKSearchResponse(
                search_data=WDKSearch(url_segment=ctx.search_name),
                validation=StepValidation(level="NONE", is_valid=False),
            ),
            ctx.record_type,
        )

    client = MagicMock()
    client.get_search_details = _details
    monkeypatch.setattr(searches, "get_wdk_client", lambda _site: client)
    monkeypatch.setattr(frame_spec, "fetch_search_details", _catalog_details)
    monkeypatch.setattr(frame_spec, "resolve_params_with_intent", _resolve)
    monkeypatch.setattr(frame_spec, "validate_parameters", _validate)
    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)
    no_count(monkeypatch)
    return returned(
        await frame_spec.set_criterion(
            _ctx(state),
            criterion_id="expression",
            text="top 10 percent of expression",
            search_name="GenesByMicroarray",
            params={},
        ),
        SetCriterionResult,
    )


class TestTheToolReportsWhatItDefaulted:
    @pytest.mark.asyncio
    async def test_a_defaulted_param_is_named(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = await _bind(monkeypatch, AgentToolState())

        assert result.defaulted_params == ["min_expression_percentile"]

    @pytest.mark.asyncio
    async def test_a_stated_param_is_not_named(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = await _bind(monkeypatch, AgentToolState())

        assert "organism" not in result.defaulted_params

    @pytest.mark.asyncio
    async def test_the_value_is_still_reported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Naming the param is not enough; the reply has to state the value used.
        result = await _bind(monkeypatch, AgentToolState())

        assert result.resolved_params["min_expression_percentile"] == "80"


class TestTheSpecRemembers:
    @pytest.mark.asyncio
    async def test_the_criterion_carries_the_defaulted_names(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Later phases report to the user, so the spec has to keep this.
        state = AgentToolState()

        await _bind(monkeypatch, state)

        criterion = state.operational_spec_draft.criteria[0]
        assert criterion.defaulted_params == ["min_expression_percentile"]
