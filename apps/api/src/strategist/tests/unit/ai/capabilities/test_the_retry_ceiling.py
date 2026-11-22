from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.toolsets.function import FunctionToolset
from veupathdb.errors import WDKError

from strategist.ai.agents.tool_vocabulary import SEARCH_LOOKUP_TOOLS
from strategist.ai.capabilities.resilience import (
    DEFAULT_CIRCUIT_BREAK_THRESHOLD,
    ToolResilience,
    TransientRetry,
)
from strategist.ai.graph.runtime import (
    OUTAGE_GIVE_UP_THRESHOLD,
    AgentDeps,
    ServiceOutageMemory,
)
from strategist.ai.graph.turn_records import TurnMarkers
from strategist.domain.strategy.session import StrategySession
from strategist.tests.unit.ai.capabilities.test_resilience import (
    _make_call,
    _make_ctx,
    _make_tool_def,
)


def _failed_before(ctx: MagicMock, tool_name: str) -> None:
    for _ in range(DEFAULT_CIRCUIT_BREAK_THRESHOLD):
        ctx.deps.service_outage.record_tool_failure(tool_name)


class TestTheRetryCeiling:
    """At the ceiling the tool stays offered and the call reads a directive."""

    @pytest.mark.asyncio
    async def test_the_breaker_answers_the_failure_after_the_threshold(self) -> None:
        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        error = WDKError("No address associated with hostname", status=502)

        async def _fail() -> Any:
            return await capability.on_tool_execute_error(
                ctx,
                call=_make_call("list_searches"),
                tool_def=_make_tool_def("list_searches"),
                args={},
                error=error,
            )

        for _ in range(DEFAULT_CIRCUIT_BREAK_THRESHOLD):
            with pytest.raises(TransientRetry):
                await _fail()
        answered = await _fail()

        assert DEFAULT_CIRCUIT_BREAK_THRESHOLD == 3
        assert "ERROR: SEARCH_UNAVAILABLE" in answered

    @pytest.mark.asyncio
    async def test_a_tool_at_its_ceiling_is_still_offered(self) -> None:
        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        ctx.retries = {"get_record_types": 3}
        tool_defs = [
            _make_tool_def("get_record_types"),
            _make_tool_def("list_searches"),
        ]
        result = await capability.prepare_tools(ctx, tool_defs)
        assert result == tool_defs

    @pytest.mark.asyncio
    async def test_a_call_at_the_ceiling_returns_the_outage_directive(self) -> None:
        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        _failed_before(ctx, "set_criterion")
        result: Any = await capability.on_tool_execute_error(
            ctx,
            call=_make_call("set_criterion"),
            tool_def=_make_tool_def("set_criterion"),
            args={"search_name": "GenesByTaxon"},
            error=WDKError("All connection attempts failed", status=502),
        )
        assert isinstance(result, str)
        assert "ERROR: SEARCH_UNAVAILABLE" in result
        assert "GenesByTaxon" in result
        assert "may recover" in result.lower()

    @pytest.mark.asyncio
    async def test_a_call_with_no_search_name_names_the_tool(self) -> None:
        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        _failed_before(ctx, "list_searches")
        result: Any = await capability.on_tool_execute_error(
            ctx,
            call=_make_call("list_searches"),
            tool_def=_make_tool_def("list_searches"),
            args={},
            error=WDKError("No address associated with hostname", status=502),
        )
        assert isinstance(result, str)
        assert "ERROR: SEARCH_UNAVAILABLE" in result
        assert "'list_searches' returned repeated transient server errors" in result

    @pytest.mark.asyncio
    async def test_an_empty_search_name_is_no_search(self) -> None:
        """An unnamed search is never given up on by name."""
        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        ctx.deps.service_outage = ServiceOutageMemory()
        error = WDKError("server error", status=500)
        for _ in range(OUTAGE_GIVE_UP_THRESHOLD):
            with pytest.raises(TransientRetry):
                await capability.on_tool_execute_error(
                    ctx,
                    call=_make_call("set_criterion"),
                    tool_def=_make_tool_def("set_criterion"),
                    args={"search_name": ""},
                    error=error,
                )
        assert ctx.deps.service_outage.unavailable_searches() == frozenset()

    @pytest.mark.asyncio
    async def test_a_turn_whose_tool_never_recovers_still_finishes(self) -> None:
        """The outage ends the tool call, not the turn."""
        requests: list[int] = []

        def _respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            del messages, info
            requests.append(len(requests))
            if len(requests) > 4:
                return ModelResponse(parts=[TextPart(content="asked the user")])
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="read_catalog",
                        args={},
                        tool_call_id=f"tc_{len(requests)}",
                    )
                ]
            )

        blackout = WDKError("All connection attempts failed", status=502)

        async def read_catalog(ctx: RunContext[AgentDeps]) -> str:
            del ctx
            raise blackout

        agent: Agent[AgentDeps, str] = Agent(
            FunctionModel(_respond),
            deps_type=AgentDeps,
            toolsets=[FunctionToolset[AgentDeps](tools=[read_catalog])],
            capabilities=[ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)],
            retries=3,
        )
        result = await agent.run(
            "read the catalog",
            deps=AgentDeps(
                site_id="plasmodb",
                strategy_session=StrategySession("plasmodb"),
                turn_markers=TurnMarkers(),
            ),
        )
        assert result.output == "asked the user"
        assert len(requests) == 5
