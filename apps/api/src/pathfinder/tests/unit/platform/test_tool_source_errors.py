from __future__ import annotations

from typing import Any, Self

import pytest
from assistant_core.mcp.admission import AdmissionRecord
from prometheus_client import REGISTRY
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset

from pathfinder.platform.tool_sources import MeteredToolSource, metered_mcp_toolset

_SOURCE = "probe-source"


class _SourceDownError(RuntimeError):
    pass


def _errors(stage: str) -> float:
    return (
        REGISTRY.get_sample_value(
            "pathfinder_tool_source_errors_total", {"source": _SOURCE, "stage": stage}
        )
        or 0.0
    )


def down() -> str:
    raise _SourceDownError


def ask_again() -> str:
    msg = "ask again with another argument"
    raise ModelRetry(msg)


class _Unreachable(WrapperToolset[Any]):
    async def __aenter__(self) -> Self:
        raise _SourceDownError


async def test_a_call_that_raises_counts_once_under_its_source() -> None:
    before = _errors("call")
    agent = Agent(
        TestModel(call_tools=["down"]),
        toolsets=[MeteredToolSource(FunctionToolset([down]), source_id=_SOURCE)],
    )

    with pytest.raises(_SourceDownError):
        await agent.run("go")

    assert _errors("call") == before + 1


async def test_a_retry_the_tool_asks_for_is_no_source_error() -> None:
    before = _errors("call")
    agent = Agent(
        TestModel(call_tools=["ask_again"]),
        toolsets=[MeteredToolSource(FunctionToolset([ask_again]), source_id=_SOURCE)],
    )

    with pytest.raises(UnexpectedModelBehavior):
        await agent.run("go")

    assert _errors("call") == before


async def test_a_source_that_does_not_open_counts_under_open() -> None:
    before = _errors("open")
    inner: AbstractToolset[Any] = _Unreachable(FunctionToolset([down]))

    with pytest.raises(_SourceDownError):
        async with MeteredToolSource(inner, source_id=_SOURCE):
            pass

    assert _errors("open") == before + 1


def test_the_builder_meters_the_admitted_server_by_its_id() -> None:
    record = AdmissionRecord(
        source_id=_SOURCE,
        endpoint="http://probe-mcp:8100/mcp",
        credential_mode="service",
        part_namespace="probe",
        max_call_seconds=30,
    )

    built = metered_mcp_toolset(record, "secret")

    assert isinstance(built, MeteredToolSource)
    assert built.source_id == _SOURCE
    assert isinstance(built.wrapped, MCPToolset)
