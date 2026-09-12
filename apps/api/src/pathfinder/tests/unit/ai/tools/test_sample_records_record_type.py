"""The sample-record tool names the record type its own session carries."""

from __future__ import annotations

import pytest
from veupathdb_mcp.wdk import SampleRecordsResult

from pathfinder.ai.tools.standalone import results
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.tool_returns import returned

from .conftest import agent_run_context


def _session(record_type: str | None) -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    if record_type is not None:
        graph = StrategyGraph("g1", "kinases", "plasmodb")
        graph.record_type = record_type
        session.add_graph(graph)
    return session


def _record_attributes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every record type the tool asks for sample attributes under."""
    seen: list[str] = []

    def attributes(record_type: str) -> list[str]:
        seen.append(record_type)
        return ["primary_key"]

    async def sample(
        site_id: str, step_id: int, *, limit: int, attributes: list[str]
    ) -> SampleRecordsResult:
        del site_id, limit, attributes
        return SampleRecordsResult(step_id=step_id, total_count=0)

    monkeypatch.setattr(results, "gene_sample_attributes", attributes)
    monkeypatch.setattr(results, "step_sample_records", sample)
    return seen


async def test_a_session_with_no_record_type_asks_for_transcript_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _record_attributes(monkeypatch)

    await results.get_sample_records(
        agent_run_context(strategy_session=_session(None)), 42
    )

    assert seen == ["transcript"]


async def test_a_session_names_its_own_record_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _record_attributes(monkeypatch)

    result = await results.get_sample_records(
        agent_run_context(strategy_session=_session("popsetSequence")), 42
    )

    assert seen == ["popsetSequence"]
    assert returned(result, SampleRecordsResult).step_id == 42
