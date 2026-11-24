"""Ranking public strategies falls back to lexical token overlap.

An unreachable embedding API costs a ranking, never a call, at every caller of
``rank_public_strategies_semantic``.
"""

from __future__ import annotations

from typing import Any

import pytest
from assistant_core.platform.types import JSONObject
from pydantic_ai import ToolFailed
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKStrategySummary
from veupathdb_mcp import tool_payloads
from veupathdb_mcp.embeddings import EmbeddingUnavailableError
from veupathdb_mcp.tools import catalog_tools

from strategist.ai.agents.tool_vocabulary import READ_ONLY_TOOLS
from strategist.ai.capabilities.site_reads import SiteReadFailures
from strategist.ai.tools.standalone import catalog
from strategist.tests._support.run_context import run_context_for
from strategist.tests._support.tool_returns import returned
from strategist.tests.unit.ai.tools.conftest import agent_run_context

_STRATEGIES = [
    WDKStrategySummary(
        strategy_id=1,
        name="Vaccine antigens",
        root_step_id=1,
        description="surface proteins",
    ),
    WDKStrategySummary(
        strategy_id=2,
        name="Kinase inhibitors",
        root_step_id=2,
        description="drug targets",
    ),
]


class _StrategyApi:
    async def list_public_strategies(self) -> list[WDKStrategySummary]:
        return list(_STRATEGIES)


@pytest.fixture(autouse=True)
def _refuse_the_embedding_api(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _refuse(*args: object, **kwargs: object) -> list[dict[str, Any]]:
        del args, kwargs
        raise EmbeddingUnavailableError(batch_size=1, cause="no route to host")

    monkeypatch.setattr(tool_payloads, "get_strategy_api", lambda _site: _StrategyApi())
    monkeypatch.setattr(tool_payloads, "rank_public_strategies_semantic", _refuse)


async def test_the_mcp_tool_falls_back_to_lexical_ranking() -> None:
    found = await catalog_tools.search_example_plans("plasmodb", "vaccine", limit=3)

    assert [row["name"] for row in found] == ["Vaccine antigens"]


async def test_the_agent_tool_falls_back_to_lexical_ranking() -> None:
    found = returned(
        await catalog.search_example_plans(agent_run_context(), "vaccine", limit=3),
        list[JSONObject],
    )

    assert [row["name"] for row in found] == ["Vaccine antigens"]


class _DownApi:
    async def list_public_strategies(self) -> list[WDKStrategySummary]:
        msg = "Request failed after retries: ReadTimeout"
        raise WDKError(msg, status=502)


async def test_a_site_that_does_not_list_its_strategies_fails_the_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tool_payloads, "get_strategy_api", lambda _site: _DownApi())
    tool = ToolDefinition(name="search_example_plans")

    with pytest.raises(WDKError) as raised:
        await catalog.search_example_plans(agent_run_context(), "vaccine", limit=3)
    with pytest.raises(ToolFailed) as failed:
        await SiteReadFailures[Any](reads=READ_ONLY_TOOLS).on_tool_execute_error(
            run_context_for(None),
            call=ToolCallPart(tool_name="search_example_plans", args={}),
            tool_def=tool,
            args={},
            error=raised.value,
        )

    assert str(failed.value).startswith(
        "search_example_plans got no answer from the site (HTTP 502:"
    )
