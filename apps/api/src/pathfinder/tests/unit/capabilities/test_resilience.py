"""Tests for error classification and the ToolResilience capability."""

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

from pathfinder.ai.agents.tool_vocabulary import SEARCH_LOOKUP_TOOLS
from pathfinder.ai.capabilities.error_classification import (
    ErrorCategory,
    build_error_directive,
    classify_error,
)
from pathfinder.ai.capabilities.resilience import ToolResilience
from pathfinder.ai.graph.runtime import ServiceOutageMemory
from pathfinder.platform.errors import (
    AppError,
    ErrorCode,
    InternalError,
    NotFoundError,
    ValidationError,
    WDKError,
)


class TestClassifyWDKError:
    """WDKError classification depends on HTTP status code."""

    def test_wdk_500_is_transient(self) -> None:
        assert (
            classify_error(WDKError("server blew up", status=500))
            == ErrorCategory.TRANSIENT
        )

    def test_wdk_502_is_transient(self) -> None:
        assert (
            classify_error(WDKError("bad gateway", status=502))
            == ErrorCategory.TRANSIENT
        )

    def test_wdk_503_is_transient(self) -> None:
        assert (
            classify_error(WDKError("service unavailable", status=503))
            == ErrorCategory.TRANSIENT
        )

    def test_wdk_400_is_semantic(self) -> None:
        assert (
            classify_error(WDKError("bad request", status=400))
            == ErrorCategory.SEMANTIC
        )

    def test_wdk_404_is_semantic(self) -> None:
        assert (
            classify_error(WDKError("not found", status=404)) == ErrorCategory.SEMANTIC
        )

    def test_wdk_422_is_semantic(self) -> None:
        assert (
            classify_error(WDKError("unprocessable", status=422))
            == ErrorCategory.SEMANTIC
        )

    def test_wdk_499_is_semantic(self) -> None:
        assert (
            classify_error(WDKError("client error", status=499))
            == ErrorCategory.SEMANTIC
        )


class TestClassifyHttpxErrors:
    """httpx network errors are TRANSIENT."""

    def test_timeout_exception_is_transient(self) -> None:
        exc = httpx.TimeoutException("timed out")
        assert classify_error(exc) == ErrorCategory.TRANSIENT

    def test_connect_error_is_transient(self) -> None:
        exc = httpx.ConnectError("connection refused")
        assert classify_error(exc) == ErrorCategory.TRANSIENT


class TestClassifyOSErrors:
    """OSError and subclasses are TRANSIENT."""

    def test_os_error_is_transient(self) -> None:
        assert classify_error(OSError("file not found")) == ErrorCategory.TRANSIENT

    def test_connection_refused_error_is_transient(self) -> None:
        assert (
            classify_error(ConnectionRefusedError("refused")) == ErrorCategory.TRANSIENT
        )

    def test_connection_error_is_transient(self) -> None:
        assert classify_error(ConnectionError("reset")) == ErrorCategory.TRANSIENT


class TestClassifyAppErrors:
    """AppError and its subclasses are SEMANTIC."""

    def test_not_found_error_is_semantic(self) -> None:
        assert classify_error(NotFoundError()) == ErrorCategory.SEMANTIC

    def test_validation_error_is_semantic(self) -> None:
        assert classify_error(ValidationError()) == ErrorCategory.SEMANTIC

    def test_generic_app_error_is_semantic(self) -> None:
        err = AppError(
            code=ErrorCode.INTERNAL_ERROR,
            title="Something went wrong",
            status=400,
        )
        assert classify_error(err) == ErrorCategory.SEMANTIC

    def test_app_error_with_500_status_is_still_semantic(self) -> None:
        """AppError classification uses the type, not the HTTP status."""
        assert classify_error(InternalError()) == ErrorCategory.SEMANTIC


class TestClassifyRuntimeErrorPermanent:
    """A RuntimeError with a config or availability message is PERMANENT."""

    def test_not_configured_is_permanent(self) -> None:
        assert (
            classify_error(RuntimeError("service not configured"))
            == ErrorCategory.PERMANENT
        )

    def test_not_available_is_permanent(self) -> None:
        assert (
            classify_error(RuntimeError("feature not available"))
            == ErrorCategory.PERMANENT
        )

    def test_not_enabled_is_permanent(self) -> None:
        assert (
            classify_error(RuntimeError("tool not enabled")) == ErrorCategory.PERMANENT
        )

    def test_service_is_disabled_is_permanent(self) -> None:
        assert (
            classify_error(RuntimeError("service is disabled"))
            == ErrorCategory.PERMANENT
        )

    def test_case_insensitive_matching(self) -> None:
        assert (
            classify_error(RuntimeError("Service Not Configured"))
            == ErrorCategory.PERMANENT
        )


class TestClassifyRuntimeErrorUnknown:
    """A RuntimeError without a config message is UNKNOWN."""

    def test_generic_runtime_error_is_unknown(self) -> None:
        assert (
            classify_error(RuntimeError("something unexpected"))
            == ErrorCategory.UNKNOWN
        )

    def test_runtime_error_with_empty_message_is_unknown(self) -> None:
        assert classify_error(RuntimeError()) == ErrorCategory.UNKNOWN


class TestClassifyUnknown:
    """Any other exception type is UNKNOWN."""

    def test_key_error_is_unknown(self) -> None:
        assert classify_error(KeyError("missing")) == ErrorCategory.UNKNOWN

    def test_type_error_is_unknown(self) -> None:
        assert classify_error(TypeError("wrong type")) == ErrorCategory.UNKNOWN

    def test_attribute_error_is_unknown(self) -> None:
        assert classify_error(AttributeError("no attr")) == ErrorCategory.UNKNOWN

    def test_value_error_is_unknown(self) -> None:
        assert classify_error(ValueError("bad value")) == ErrorCategory.UNKNOWN

    def test_exception_base_is_unknown(self) -> None:
        assert classify_error(Exception("generic")) == ErrorCategory.UNKNOWN


class TestErrorCategoryEnum:
    """ErrorCategory is a StrEnum with four members."""

    def test_enum_members(self) -> None:
        members = {e.value for e in ErrorCategory}
        assert members == {"TRANSIENT", "SEMANTIC", "PERMANENT", "UNKNOWN"}

    def test_is_str_enum(self) -> None:
        assert ErrorCategory.TRANSIENT == "TRANSIENT"
        assert ErrorCategory.SEMANTIC == "SEMANTIC"
        assert ErrorCategory.PERMANENT == "PERMANENT"
        assert ErrorCategory.UNKNOWN == "UNKNOWN"


_SAMPLE_NEXT_ACTIONS = [
    "Call search_for_searches to find the correct name",
    "Retry with the corrected search name",
]
_SAMPLE_DO_NOT = "Do not retry with the same invalid search name"
_SAMPLE_DETAIL = "Search 'GenesByBadName' does not exist on this site"


class TestBuildErrorDirectiveFormat:
    """The directive contains every required section."""

    def test_contains_error_section(self) -> None:
        directive = build_error_directive(
            error_type="WDKError (TRANSIENT)",
            tool_name="search_genes",
            tool_args={"query": "malaria"},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "ERROR:" in directive

    def test_contains_tool_section(self) -> None:
        directive = build_error_directive(
            error_type="WDKError (TRANSIENT)",
            tool_name="search_genes",
            tool_args={"query": "malaria"},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "TOOL:" in directive
        assert "search_genes" in directive

    def test_contains_next_actions_section(self) -> None:
        directive = build_error_directive(
            error_type="WDKError (TRANSIENT)",
            tool_name="search_genes",
            tool_args={"query": "malaria"},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "NEXT_ACTIONS:" in directive

    def test_contains_do_not_section(self) -> None:
        directive = build_error_directive(
            error_type="WDKError (TRANSIENT)",
            tool_name="search_genes",
            tool_args={"query": "malaria"},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "DO NOT:" in directive

    def test_contains_detail_section(self) -> None:
        detail = "server error details here"
        directive = build_error_directive(
            error_type="WDKError (TRANSIENT)",
            tool_name="search_genes",
            tool_args={},
            detail=detail,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "DETAIL:" in directive
        assert detail in directive

    def test_tool_name_appears_in_tool_line(self) -> None:
        directive = build_error_directive(
            error_type="NotFoundError (SEMANTIC)",
            tool_name="get_strategy",
            tool_args={"id": "123"},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "get_strategy" in directive

    def test_error_type_string_in_directive(self) -> None:
        directive = build_error_directive(
            error_type="WDKError (TRANSIENT)",
            tool_name="search_genes",
            tool_args={},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "WDKError (TRANSIENT)" in directive

    def test_works_with_no_args(self) -> None:
        directive = build_error_directive(
            error_type="RuntimeError (UNKNOWN)",
            tool_name="my_tool",
            tool_args={},
            detail="something unexpected",
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "TOOL:" in directive
        assert "my_tool" in directive

    def test_next_actions_appear_in_output(self) -> None:
        actions = [
            "Call search_for_searches to find the correct name",
            "Retry with the corrected search name",
        ]
        directive = build_error_directive(
            error_type="WDKError (SEMANTIC)",
            tool_name="search_genes",
            tool_args={},
            detail=_SAMPLE_DETAIL,
            next_actions=actions,
            do_not=_SAMPLE_DO_NOT,
        )
        assert actions[0] in directive
        assert actions[1] in directive

    def test_do_not_string_appears_in_output(self) -> None:
        do_not = "Do not retry with the same invalid search name"
        directive = build_error_directive(
            error_type="WDKError (SEMANTIC)",
            tool_name="search_genes",
            tool_args={},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=do_not,
        )
        assert do_not in directive

    def test_detail_string_appears_in_output(self) -> None:
        detail = "Search 'GenesByOrthologPattern' returned 0 results — check JSESSIONID"
        directive = build_error_directive(
            error_type="WDKError (SEMANTIC)",
            tool_name="search_genes",
            tool_args={},
            detail=detail,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert detail in directive

    def test_next_actions_are_numbered(self) -> None:
        actions = ["First action", "Second action", "Third action"]
        directive = build_error_directive(
            error_type="WDKError (TRANSIENT)",
            tool_name="search_genes",
            tool_args={},
            detail=_SAMPLE_DETAIL,
            next_actions=actions,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "1. First action" in directive
        assert "2. Second action" in directive
        assert "3. Third action" in directive


class TestBuildErrorDirectiveArgSanitization:
    """Long argument values are truncated to a bounded length."""

    _LONG_VALUE = "x" * 500

    def test_long_arg_value_is_truncated(self) -> None:
        directive = build_error_directive(
            error_type="NotFoundError (SEMANTIC)",
            tool_name="search_genes",
            tool_args={"query": self._LONG_VALUE},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert self._LONG_VALUE not in directive

    def test_tool_line_stays_reasonable(self) -> None:
        directive = build_error_directive(
            error_type="NotFoundError (SEMANTIC)",
            tool_name="search_genes",
            tool_args={"query": self._LONG_VALUE, "extra": self._LONG_VALUE},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        tool_line = next(
            (line for line in directive.splitlines() if line.startswith("TOOL:")),
            "",
        )
        assert len(tool_line) < 500

    def test_truncated_value_has_ellipsis(self) -> None:
        directive = build_error_directive(
            error_type="NotFoundError (SEMANTIC)",
            tool_name="search_genes",
            tool_args={"query": self._LONG_VALUE},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "..." in directive

    def test_short_args_not_truncated(self) -> None:
        directive = build_error_directive(
            error_type="NotFoundError (SEMANTIC)",
            tool_name="search_genes",
            tool_args={"query": "malaria"},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "malaria" in directive


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
