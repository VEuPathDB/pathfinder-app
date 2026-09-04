"""Ranking public strategies falls back to lexical token overlap.

An unreachable embedding API costs a ranking, never a call, at every caller of
``rank_public_strategies_semantic``.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from assistant_core.embeddings.embedder import EmbeddingUnavailableError
from pydantic_ai import RunContext

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone import catalog as catalog_tools
from pathfinder.integrations.veupathdb.wdk_models import WDKStrategySummary
from pathfinder.mcp import _catalog_tools as mcp_catalog_tools
from pathfinder.services import tool_payloads

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


class _Deps:
    site_id = "plasmodb"


class _Ctx:
    deps = _Deps()
    tool_call_id = "call_1"


@pytest.fixture(autouse=True)
def _refuse_the_embedding_api(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _refuse(*args: object, **kwargs: object) -> list[dict[str, Any]]:
        del args, kwargs
        raise EmbeddingUnavailableError(batch_size=1, cause="no route to host")

    monkeypatch.setattr(tool_payloads, "get_strategy_api", lambda _site: _StrategyApi())
    monkeypatch.setattr(tool_payloads, "rank_public_strategies_semantic", _refuse)


async def test_the_mcp_tool_falls_back_to_lexical_ranking() -> None:
    found = await mcp_catalog_tools.search_example_plans("plasmodb", "vaccine", limit=3)

    assert [row["name"] for row in found] == ["Vaccine antigens"]


async def test_the_agent_tool_falls_back_to_lexical_ranking() -> None:
    found = (
        await catalog_tools.search_example_plans(
            cast("RunContext[AgentDeps]", _Ctx()), "vaccine", limit=3
        )
    ).return_value

    assert [row["name"] for row in found] == ["Vaccine antigens"]
