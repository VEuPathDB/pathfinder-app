"""The sample-record tool names the record type its own session carries."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb_mcp.wdk import SampleRecordsResult

from pathfinder.ai.tools.standalone import _sample_page, results
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.classed_strategy import classed_strategy
from pathfinder.tests._support.tool_returns import returned

from .conftest import agent_run_context


def _session(record_type: str | None) -> StrategySession:
    if record_type is None:
        return StrategySession(site_id="plasmodb")
    return classed_strategy("plasmodb", {"step_kinases": 42}, record_type)


def _record_attributes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every record type the tool asks for sample attributes under, once
    for the gene columns and once for the columns its searches select on."""
    seen: list[str] = []

    def attributes(record_type: str) -> list[str]:
        seen.append(record_type)
        return ["primary_key"]

    async def sample(
        site_id: str,
        step_id: int,
        *,
        limit: int,
        attributes: list[str],
        record_type: str,
        seed: str,
    ) -> _sample_page.SampledRecords:
        del site_id, limit, attributes, record_type, seed
        return _sample_page.SampledRecords(
            _sample_page.StepSample(step_id=step_id, total_count=0), []
        )

    async def selected(
        site_id: str,
        record_type: str,
        graph: StrategyGraph | None,
        *,
        own_search: str | None,
    ) -> list[str]:
        del site_id, graph, own_search
        seen.append(record_type)
        return []

    monkeypatch.setattr(results, "gene_sample_attributes", attributes)
    monkeypatch.setattr(results, "sample_attributes", selected)
    monkeypatch.setattr(results, "sample_page", sample)
    return seen


async def test_a_session_with_no_record_type_reads_no_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _record_attributes(monkeypatch)

    with pytest.raises(ModelRetry) as refused:
        await results.get_sample_records(
            agent_run_context(strategy_session=_session(None)), 42
        )

    assert (seen, str(refused.value)) == (
        [],
        "Step 42 is not a step of this strategy, so it cannot be read.",
    )


async def test_a_session_names_its_own_record_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _record_attributes(monkeypatch)

    result = await results.get_sample_records(
        agent_run_context(strategy_session=_session("popsetSequence")), 42
    )

    assert seen == ["popsetSequence", "popsetSequence"]
    assert returned(result, SampleRecordsResult).step_id == 42
