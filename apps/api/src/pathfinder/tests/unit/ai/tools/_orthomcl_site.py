from __future__ import annotations

import pytest
from pydantic_ai import RunContext
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import StepValidation
from veupathdb.wdk import WDKSearch, WDKSearchResponse
from veupathdb_mcp import tool_payloads
from veupathdb_mcp.catalog import ParameterInfo, ParamFetcher, format_param_info_typed
from veupathdb_mcp.tool_payloads import SearchListing

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone import (
    _catalog_models,
    _frame_count,
    _frame_sheet,
    frame_spec,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import dataset_sources
from pathfinder.tests._support.orthomcl_site import OrthoSite
from pathfinder.tests._support.recorded_counts import no_measurements
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context
from pathfinder.tests.unit.ai.tools.test_frame_spec import no_validation


def group_strategy_session() -> StrategySession:
    session = StrategySession(site_id="orthomcl")
    graph = StrategyGraph(graph_id="g1", name="g", site_id="orthomcl")
    graph.record_type = "group"
    session.add_graph(graph)
    return session


def group_strategy_ctx(state: AgentToolState) -> RunContext[AgentDeps]:
    return agent_run_context(
        site_id="orthomcl", agent_state=state, strategy_session=group_strategy_session()
    )


def serve_orthomcl(monkeypatch: pytest.MonkeyPatch) -> OrthoSite:
    site = OrthoSite()

    def _response(search: WDKSearch) -> WDKSearchResponse:
        return WDKSearchResponse(
            search_data=search,
            validation=StepValidation(level="NONE", is_valid=False),
        )

    async def _definition(_site: str, record_type: str, name: str) -> WDKSearch:
        return site.read(record_type, name)

    async def _details(
        ctx: SearchContext, **_kw: object
    ) -> tuple[WDKSearchResponse, str]:
        return _response(site.read(ctx.record_type, ctx.search_name)), ctx.record_type

    async def _listings(_site: str, record_type: str) -> list[SearchListing]:
        return [
            SearchListing(name=s.url_segment, display_name=s.display_name)
            for s in site.held[record_type].values()
        ]

    def _fetch_at(_site: str, record_type: str, name: str) -> ParamFetcher:
        async def fetch_at(context: dict[str, str]) -> list[ParameterInfo]:
            site.contexts.append(context)
            return format_param_info_typed(
                site.read(record_type, name).parameters or []
            )

        return fetch_at

    async def _count(
        _site: str, _record_type: str, name: str, params: dict[str, ParamValue]
    ) -> int:
        return site.count(name, params)

    monkeypatch.setattr(_frame_sheet, "read_search_definition", _definition)
    monkeypatch.setattr(frame_spec, "fetch_search_details", _details)
    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)
    monkeypatch.setattr(_catalog_models, "read_search_definition", _definition)
    monkeypatch.setattr(tool_payloads, "list_search_listings", _listings)
    monkeypatch.setattr(_frame_count, "count_bound_criterion", _count)
    monkeypatch.setattr(dataset_sources, "get_strategy_api", lambda _site_id: site)
    no_validation(monkeypatch)
    no_measurements(monkeypatch)
    return site
