"""The ToolResilience capability: retries, directives and tool preparation."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets.function import FunctionToolset
from veupathdb.errors import WDKError

from pathfinder.ai.agents.tool_vocabulary import SEARCH_LOOKUP_TOOLS
from pathfinder.ai.capabilities.resilience import ToolResilience
from pathfinder.ai.graph.runtime import (
    OUTAGE_GIVE_UP_THRESHOLD,
    AgentDeps,
    ServiceOutageMemory,
)
from pathfinder.domain.strategy.session import StrategySession


def _make_ctx() -> MagicMock:
    ctx: MagicMock = MagicMock()
    ctx.deps = MagicMock()
    ctx.deps.site_id = "plasmodb.org"
    ctx.retries = {}
    return ctx


def _make_call(tool_name: str = "get_search_overview") -> ToolCallPart:
    return ToolCallPart(
        tool_name=tool_name, args='{"search_name":"Foo"}', tool_call_id="tc_1"
    )


def _make_tool_def(name: str = "get_search_overview") -> ToolDefinition:
    return ToolDefinition(name=name, description="test", parameters_json_schema={})


class TestOnToolExecuteError:
    """ToolResilience.on_tool_execute_error routes by error category."""

    @pytest.mark.asyncio
    async def test_wdk_404_returns_directive_string(self) -> None:
        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        error = WDKError("search not found", status=404)
        result: Any = await capability.on_tool_execute_error(
            ctx,
            call=_make_call("get_search_overview"),
            tool_def=_make_tool_def("get_search_overview"),
            args={"search_name": "Foo"},
            error=error,
        )
        assert isinstance(result, str)
        assert "SEARCH_NOT_FOUND" in result
        assert "NEXT_ACTIONS" in result
        assert "search_for_searches" in result

    @pytest.mark.asyncio
    async def test_wdk_500_raises_model_retry(self) -> None:
        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        error = WDKError("server error", status=500)
        with pytest.raises(ModelRetry):
            await capability.on_tool_execute_error(
                ctx,
                call=_make_call(),
                tool_def=_make_tool_def(),
                args={},
                error=error,
            )

    @pytest.mark.asyncio
    async def test_timeout_raises_model_retry(self) -> None:
        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        error = httpx.TimeoutException("connection timed out")
        with pytest.raises(ModelRetry):
            await capability.on_tool_execute_error(
                ctx,
                call=_make_call(),
                tool_def=_make_tool_def(),
                args={},
                error=error,
            )

    @pytest.mark.asyncio
    async def test_unknown_error_returns_generic_directive(self) -> None:
        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        error = KeyError("missing key")
        result: Any = await capability.on_tool_execute_error(
            ctx,
            call=_make_call(),
            tool_def=_make_tool_def(),
            args={},
            error=error,
        )
        assert isinstance(result, str)
        assert "ERROR:" in result
        assert "INTERNAL_TOOL_ERROR" in result

    @pytest.mark.asyncio
    async def test_persistent_5xx_on_same_search_gives_up_after_threshold(self) -> None:
        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        ctx.deps.service_outage = ServiceOutageMemory()
        error = WDKError("server error", status=500)

        async def _call() -> Any:
            return await capability.on_tool_execute_error(
                ctx,
                call=_make_call("get_search_overview"),
                tool_def=_make_tool_def("get_search_overview"),
                args={"search_name": "GenesByRNASeqFoo"},
                error=error,
            )

        with pytest.raises(ModelRetry):
            await _call()
        result = await _call()
        assert isinstance(result, str)
        assert "GenesByRNASeqFoo" in result
        assert "different search" in result.lower()
        # A TRANSIENT error is never reported to the agent as permanent.
        assert "down, not transient" not in result.lower()
        assert "may recover" in result.lower()

    @pytest.mark.asyncio
    async def test_persistent_5xx_tracks_searches_independently(self) -> None:
        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        ctx.deps.service_outage = ServiceOutageMemory()
        error = WDKError("server error", status=500)
        for name in ("Foo", "Bar"):
            with pytest.raises(ModelRetry):
                await capability.on_tool_execute_error(
                    ctx,
                    call=_make_call("get_search_overview"),
                    tool_def=_make_tool_def("get_search_overview"),
                    args={"search_name": name},
                    error=error,
                )

    @pytest.mark.asyncio
    async def test_transient_without_search_name_still_retries(self) -> None:
        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        ctx.deps.service_outage = ServiceOutageMemory()
        error = WDKError("server error", status=500)
        for _ in range(3):
            with pytest.raises(ModelRetry):
                await capability.on_tool_execute_error(
                    ctx,
                    call=_make_call(),
                    tool_def=_make_tool_def(),
                    args={},
                    error=error,
                )

    @pytest.mark.asyncio
    async def test_permanent_error_returns_service_unavailable(self) -> None:
        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        error = RuntimeError("Web search service not configured")
        result: Any = await capability.on_tool_execute_error(
            ctx,
            call=_make_call(),
            tool_def=_make_tool_def(),
            args={},
            error=error,
        )
        assert isinstance(result, str)
        assert "SERVICE_UNAVAILABLE" in result


class TestTheRetryCeiling:
    """At the ceiling the tool stays offered and the call reads a directive."""

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
        ctx.deps.service_outage = ServiceOutageMemory()
        ctx.retries = {"set_criterion": 3}
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
        ctx.deps.service_outage = ServiceOutageMemory()
        ctx.retries = {"list_searches": 3}
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
        for _ in range(OUTAGE_GIVE_UP_THRESHOLD + 1):
            with pytest.raises(ModelRetry):
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
                site_id="plasmodb", strategy_session=StrategySession("plasmodb")
            ),
        )
        assert result.output == "asked the user"
        assert len(requests) == 5


class TestOnToolValidateError:
    """on_tool_validate_error adds a shape hint to argument errors."""

    @pytest.mark.asyncio
    async def test_misplaced_secondary_input_raises_helpful_model_retry(
        self,
    ) -> None:
        class _ArgsModel(BaseModel):
            model_config = ConfigDict(extra="forbid")
            root: dict[str, Any]

        try:
            _ArgsModel.model_validate(
                {"root": {}, "secondaryInput": {"searchName": "X"}},
            )
            pytest.fail("expected ValidationError")
        except PydanticValidationError as exc:
            error = exc

        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        with pytest.raises(ModelRetry) as excinfo:
            await capability.on_tool_validate_error(
                ctx,
                call=_make_call("build_strategy"),
                tool_def=_make_tool_def("build_strategy"),
                args={"root": {}, "secondaryInput": {"searchName": "X"}},
                error=error,
            )
        msg = str(excinfo.value)
        assert "secondaryInput" in msg
        assert "INSIDE `root`" in msg
        assert "primaryInput" in msg

    @pytest.mark.asyncio
    async def test_clean_args_propagate_original_error(self) -> None:
        class _ArgsModel(BaseModel):
            model_config = ConfigDict(extra="forbid")
            root: dict[str, Any]

        try:
            _ArgsModel.model_validate({})
            pytest.fail("expected ValidationError")
        except PydanticValidationError as exc:
            error = exc

        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        with pytest.raises(PydanticValidationError):
            await capability.on_tool_validate_error(
                ctx,
                call=_make_call("build_strategy"),
                tool_def=_make_tool_def("build_strategy"),
                args={},
                error=error,
            )

    @pytest.mark.asyncio
    async def test_other_tools_propagate_unchanged(self) -> None:
        class _ArgsModel(BaseModel):
            x: int

        try:
            _ArgsModel.model_validate({"x": "not-an-int", "primaryInput": {}})
            pytest.fail("expected ValidationError")
        except PydanticValidationError as exc:
            error = exc

        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        with pytest.raises(PydanticValidationError):
            await capability.on_tool_validate_error(
                ctx,
                call=_make_call("some_other_tool"),
                tool_def=_make_tool_def("some_other_tool"),
                args={"x": "not-an-int", "primaryInput": {}},
                error=error,
            )

    @pytest.mark.asyncio
    async def test_set_problem_frame_wrapped_args_raises_helpful_hint(self) -> None:
        class _ArgsModel(BaseModel):
            model_config = ConfigDict(extra="forbid")
            userGoal: str
            interpretedGoal: str

        wrapped_args: dict[str, Any] = {
            "frame": {
                "userGoal": "Find genes",
                "interpretedGoal": "Identify P. falciparum genes",
            },
        }
        try:
            _ArgsModel.model_validate(wrapped_args)
            pytest.fail("expected ValidationError")
        except PydanticValidationError as exc:
            error = exc

        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        with pytest.raises(ModelRetry) as excinfo:
            await capability.on_tool_validate_error(
                ctx,
                call=_make_call("set_problem_frame"),
                tool_def=_make_tool_def("set_problem_frame"),
                args=wrapped_args,
                error=error,
            )
        msg = str(excinfo.value)
        assert "frame" in msg
        assert "top" in msg.lower()
        assert "set_problem_frame" in msg

    @pytest.mark.asyncio
    async def test_wrapped_args_hint_works_for_any_tool(self) -> None:
        class _ArgsModel(BaseModel):
            model_config = ConfigDict(extra="forbid")
            query: str
            top_k: int

        wrapped_args: dict[str, Any] = {
            "input": {"query": "kinase", "top_k": 10},
        }
        try:
            _ArgsModel.model_validate(wrapped_args)
            pytest.fail("expected ValidationError")
        except PydanticValidationError as exc:
            error = exc

        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        with pytest.raises(ModelRetry) as excinfo:
            await capability.on_tool_validate_error(
                ctx,
                call=_make_call("search_tool"),
                tool_def=_make_tool_def("search_tool"),
                args=wrapped_args,
                error=error,
            )
        msg = str(excinfo.value)
        assert "input" in msg
        assert "search_tool" in msg
