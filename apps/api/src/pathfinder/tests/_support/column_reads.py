"""A site that answers a check's column reports from the recorded bodies."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic import JsonValue
from pydantic_ai import RunContext
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import MultiPickValue, ParamValue, StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import (
    WDKColumnDistribution,
    WDKRecordType,
    WDKSearch,
    WDKSearchResponse,
)

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone import results
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.value_binding import bind_values
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.recorded_columns import (
    PERCENTILE_SEARCH,
    PERCENTILE_STEP,
    catalog_search,
    column_catalog,
    recorded_body,
)
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

TM_TEXT = "two or more transmembrane domains"


class ColumnSite:
    """The site's column reports, answered from the recorded bodies."""

    def __init__(
        self,
        columns: Mapping[str, WDKColumnDistribution],
        reports: Mapping[str, JsonValue],
    ) -> None:
        self.columns = columns
        self.reports = reports
        self.asked: list[str] = []
        self.budgets: list[float | None] = []

    async def get_column_distribution(
        self, step_id: int, column_name: str, *, budget_seconds: float | None = None
    ) -> WDKColumnDistribution:
        self.asked.append(f"{step_id}/columns/{column_name}")
        self.budgets.append(budget_seconds)
        return self.columns.get(column_name, WDKColumnDistribution())

    async def run_step_report(self, step_id: int, report_name: str) -> JsonValue:
        self.asked.append(f"{step_id}/reports/{report_name}")
        return self.reports[report_name]


# The parameter types plasmodb reports: every numeric threshold is a string
# that is a number, and a text expression is a string that is not.
_NUMERIC = frozenset(
    {"min_tm", "max_tm", "min_expression_percentile", "max_expression_percentile"}
)


class _Definitions:
    """The expanded search definitions, with the parameters the tests bind."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def get_search_details(self, ctx: SearchContext) -> WDKSearchResponse:
        self.asked.append(ctx.search_name)
        search = catalog_search(ctx.search_name)
        return WDKSearchResponse.model_validate(
            {
                "searchData": {
                    "urlSegment": search.url_segment,
                    "parameters": [
                        {"name": n, "type": "string", "isNumber": n in _NUMERIC}
                        for n in search.param_names
                    ],
                },
                "validation": {"level": "DISPLAYABLE", "isValid": True},
            }
        )


def serve_columns(monkeypatch: pytest.MonkeyPatch, site: ColumnSite) -> None:
    catalog = column_catalog()
    definitions = _Definitions()

    async def searches(site_id: str, record_type: str) -> list[WDKSearch]:
        del site_id, record_type
        return list(catalog.searches or [])

    async def record_types(site_id: str) -> list[WDKRecordType]:
        del site_id
        return [catalog]

    monkeypatch.setattr(results, "get_raw_searches", searches)
    monkeypatch.setattr(results, "get_raw_record_types", record_types)
    monkeypatch.setattr(results, "get_strategy_api", lambda site_id: site)
    monkeypatch.setattr(results, "get_discovery_service", lambda: definitions)


def column_context(
    search_name: str,
    wdk_step_id: int,
    params: Mapping[str, ParamValue],
) -> RunContext[AgentDeps]:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Membrane", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(StrategyStepNode(id="c_one", search_name=search_name))
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(wdk_step_ids={"c_one": wdk_step_id})
    criterion = Criterion(
        id="c_one",
        text=TM_TEXT,
        search_name=search_name,
        resolved_params=bind_values(params, "stated", []),
    )
    state = AgentToolState(operational_spec_draft=OperationalSpec(criteria=[criterion]))
    return agent_run_context(strategy_session=session, agent_state=state)


TM_PARAMS: dict[str, ParamValue] = {
    "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"]),
    "min_tm": StringValue(value="2"),
    "max_tm": StringValue(value="99"),
}


def percentile_site() -> ColumnSite:
    return ColumnSite(
        {},
        {
            "min_percentile_chosen-histogram": recorded_body(
                "step_report_min_percentile_chosen_histogram"
            ),
            "max_percentile_chosen-histogram": recorded_body(
                "step_report_max_percentile_chosen_histogram"
            ),
        },
    )


def percentile_context(low: str) -> RunContext[AgentDeps]:
    return column_context(
        PERCENTILE_SEARCH,
        PERCENTILE_STEP,
        {
            "min_expression_percentile": StringValue(value=low),
            "max_expression_percentile": StringValue(value="100"),
        },
    )
