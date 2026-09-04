"""``ValidatingEnumToolset`` keeps the tool schema static and enforces the
allowed set at call time, so the prompt-cache prefix survives discovery."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.usage import RunUsage

from pathfinder.ai.tools.toolsets._dynamic import (
    EnumOverrides,
    ValidatingEnumToolset,
)


def _stub_model() -> FunctionModel:
    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        return ModelResponse(parts=[TextPart(content="ok")])

    async def _stream(
        messages: list[ModelMessage],
        info: AgentInfo,
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        del messages, info
        yield "ok"

    return FunctionModel(_fn, stream_function=_stream, model_name="test")


def _ctx() -> RunContext[None]:
    return RunContext(deps=None, model=_stub_model(), usage=RunUsage())


async def _inspect(ctx: RunContext[None], search_name: str) -> str:
    del ctx
    return f"OK:{search_name}"


def _build(overrides: EnumOverrides) -> ValidatingEnumToolset[None]:
    base: FunctionToolset[None] = FunctionToolset(tools=[_inspect])
    return ValidatingEnumToolset(wrapped=base, build_overrides=lambda _ctx: overrides)


@pytest.mark.asyncio
async def test_schema_carries_no_enum() -> None:
    """A constant schema keeps the prompt-cache prefix stable."""
    toolset = _build({("_inspect", "search_name"): ["GenesByText", "GenesByGoTerm"]})
    tools = await toolset.get_tools(_ctx())
    schema: dict[str, Any] = dict(tools["_inspect"].tool_def.parameters_json_schema)
    assert "enum" not in schema["properties"]["search_name"]


@pytest.mark.asyncio
async def test_valid_value_delegates() -> None:
    toolset = _build({("_inspect", "search_name"): ["GenesByText", "GenesByGoTerm"]})
    ctx = _ctx()
    tool = (await toolset.get_tools(ctx))["_inspect"]
    result = await toolset.call_tool(
        "_inspect", {"search_name": "GenesByText"}, ctx, tool
    )
    assert result == "OK:GenesByText"


@pytest.mark.asyncio
async def test_invalid_value_raises_model_retry_naming_valid() -> None:
    toolset = _build({("_inspect", "search_name"): ["GenesByText", "GenesByGoTerm"]})
    ctx = _ctx()
    tool = (await toolset.get_tools(ctx))["_inspect"]
    with pytest.raises(ModelRetry) as exc:
        await toolset.call_tool("_inspect", {"search_name": "Imaginary"}, ctx, tool)
    msg = str(exc.value)
    assert "Imaginary" in msg
    assert "GenesByText" in msg
    assert "GenesByGoTerm" in msg


@pytest.mark.asyncio
async def test_no_override_means_unconstrained() -> None:
    """The builder yields nothing on a cold start, so any value delegates."""
    toolset = _build({})
    ctx = _ctx()
    tool = (await toolset.get_tools(ctx))["_inspect"]
    result = await toolset.call_tool(
        "_inspect", {"search_name": "AnythingGoes"}, ctx, tool
    )
    assert result == "OK:AnythingGoes"


@pytest.mark.asyncio
async def test_unrelated_arg_not_validated() -> None:
    """An override keyed on a different tool must not constrain this one."""
    toolset = _build({("some_other_tool", "search_name"): ["X"]})
    ctx = _ctx()
    tool = (await toolset.get_tools(ctx))["_inspect"]
    result = await toolset.call_tool(
        "_inspect", {"search_name": "FreeValue"}, ctx, tool
    )
    assert result == "OK:FreeValue"
