from __future__ import annotations

import logging
from typing import Any, Self

import pytest
from assistant_core.mcp.admission import AdmissionRecord, AdmittedSources
from prometheus_client import REGISTRY
from pydantic import BaseModel, ConfigDict
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset

from strategist.ai.capabilities import screened_sources
from strategist.ai.capabilities.screened_sources import ScreenedToolSources
from strategist.platform.tool_sources import (
    RESEARCH_MCP_SOURCE_ID,
    RESEARCH_TOOL_SOURCE,
)

_RECORD = AdmissionRecord(
    source_id=RESEARCH_MCP_SOURCE_ID,
    endpoint="http://research-mcp:8110/mcp",
    credential_mode="service",
    part_namespace="research",
    max_call_seconds=30,
)


class _Unresolved(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event: str
    source_id: str
    reason: str


class _SourceDownError(RuntimeError):
    pass


class _Unreachable(WrapperToolset[Any]):
    async def __aenter__(self) -> Self:
        raise _SourceDownError


def _unreachable(
    record: AdmissionRecord, credential: str | None
) -> AbstractToolset[Any]:
    del record, credential
    return _Unreachable(FunctionToolset())


def _reachable(record: AdmissionRecord, credential: str | None) -> AbstractToolset[Any]:
    del record, credential
    return FunctionToolset()


def _unresolved_count() -> float:
    return (
        REGISTRY.get_sample_value(
            "pathfinder_tool_source_errors_total",
            {"source": RESEARCH_MCP_SOURCE_ID, "stage": "unresolved"},
        )
        or 0.0
    )


def _warnings(caplog: pytest.LogCaptureFixture) -> list[_Unresolved]:
    return [
        _Unresolved.model_validate(record.msg)
        for record in caplog.records
        if record.name == screened_sources.__name__
        and record.levelno == logging.WARNING
    ]


def _sources(admitted: AdmittedSources, build: Any) -> ScreenedToolSources:
    return ScreenedToolSources(
        declarations=(RESEARCH_TOOL_SOURCE,),
        credential=lambda record: "secret",
        admitted=admitted,
        build_toolset=build,
    )


async def test_a_source_the_deployment_does_not_admit_counts_each_turn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    before = _unresolved_count()

    for _ in range(2):
        async with _sources(AdmittedSources(), _reachable) as resolved:
            assert dict(resolved.by_name) == {}

    assert _unresolved_count() == before + 2
    assert [(w.source_id, w.reason) for w in _warnings(caplog)] == [
        (RESEARCH_MCP_SOURCE_ID, "not admitted"),
        (RESEARCH_MCP_SOURCE_ID, "not admitted"),
    ]


async def test_a_source_that_does_not_open_counts_as_unresolved(
    caplog: pytest.LogCaptureFixture,
) -> None:
    before = _unresolved_count()

    async with _sources(AdmittedSources(records=(_RECORD,)), _unreachable) as resolved:
        assert dict(resolved.by_name) == {}

    assert _unresolved_count() == before + 1
    assert [(w.source_id, w.reason) for w in _warnings(caplog)] == [
        (RESEARCH_MCP_SOURCE_ID, "did not open"),
    ]


async def test_a_source_that_resolves_counts_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    before = _unresolved_count()

    async with _sources(AdmittedSources(records=(_RECORD,)), _reachable) as resolved:
        assert sorted(resolved.by_name) == [RESEARCH_TOOL_SOURCE.name]

    assert _unresolved_count() == before
    assert _warnings(caplog) == []
