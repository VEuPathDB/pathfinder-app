"""Ranking public strategies falls back to lexical token overlap.

An unreachable embedding API costs a ranking, never a call, at every caller of
``rank_public_strategies_semantic``.
"""

from __future__ import annotations

from typing import Any

import pytest
from assistant_core.platform.types import JSONObject
from veupathdb.wdk.wdk_models import WDKStrategySummary
from veupathdb_mcp import tool_payloads
from veupathdb_mcp.embeddings import EmbeddingUnavailableError
from veupathdb_mcp.tools import catalog_tools

from pathfinder.ai.tools.standalone import catalog
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

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
