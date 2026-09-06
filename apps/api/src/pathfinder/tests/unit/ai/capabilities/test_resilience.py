"""The ToolResilience capability: retries, directives and tool preparation."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition
from veupathdb.errors import WDKError

from pathfinder.ai.agents.tool_vocabulary import SEARCH_LOOKUP_TOOLS
from pathfinder.ai.capabilities.resilience import ToolResilience
from pathfinder.ai.graph.runtime import ServiceOutageMemory


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


class TestPrepareTools:
    """prepare_tools removes a tool that exceeds the retry threshold."""

    @pytest.mark.asyncio
    async def test_removes_tool_after_threshold(self) -> None:
        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        ctx.retries = {"get_record_types": 3}
        tool_defs = [
            _make_tool_def("get_record_types"),
            _make_tool_def("list_searches"),
        ]
        result = await capability.prepare_tools(ctx, tool_defs)
        names = [td.name for td in result]
        assert "get_record_types" not in names
        assert "list_searches" in names

    @pytest.mark.asyncio
    async def test_keeps_tools_below_threshold(self) -> None:
        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        ctx.retries = {"get_record_types": 2}
        tool_defs = [
            _make_tool_def("get_record_types"),
            _make_tool_def("list_searches"),
        ]
        result = await capability.prepare_tools(ctx, tool_defs)
        names = [td.name for td in result]
        assert "get_record_types" in names
        assert "list_searches" in names

    @pytest.mark.asyncio
    async def test_no_retries_keeps_all_tools(self) -> None:
        capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
        ctx = _make_ctx()
        ctx.retries = {}
        tool_defs = [
            _make_tool_def("get_record_types"),
            _make_tool_def("list_searches"),
        ]
        result = await capability.prepare_tools(ctx, tool_defs)
        assert result == tool_defs


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
