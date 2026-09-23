"""A sub-agent's research reads are recorded and billed like the Lead's.

FRAME and VERIFY read the same served research tools the Lead reads. A
reference one of them retrieves is a reference the turn retrieved, and a search
the deployment paid for is on the turn's bill whoever asked for it.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest
from pydantic_ai.toolsets import FunctionToolset

from pathfinder.ai.graph._lead_capture import _LeadRunCapture, usage_recorders
from pathfinder.ai.graph.runtime import AgentDeps, turn_tool_sources
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.reply_claims import CitedSource
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import (
    LeadResponse,
    hold_the_turn_contract,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    lead_deps,
    pipeline_state,
)

_DOI = "10.1371/journal.ppat.1010773"
_PRICE = Decimal("0.005")
_PAPER = (
    '{"query": "ROP18 kinase", "results": [{"title": "ROP18 is a rhoptry kinase", '
    f'"doi": "{_DOI}", "pmid": null, "url": null}}], '
    '"sources": [], "sourcesStatus": [], "guidance": "", "costUsd": "0.005"}'
)


def _served_research() -> FunctionToolset[Any]:
    inner: FunctionToolset[Any] = FunctionToolset()

    def literature(query: str) -> str:
        del query
        return _PAPER

    inner.add_function(literature, name="research_literature_search")
    return inner


async def _read_a_paper(agent_deps: AgentDeps) -> None:
    """Call the served tool the way the sub-agent's own run would."""
    ctx = run_context_for(agent_deps, tool_call_id="inner_lit")
    sources = turn_tool_sources(ctx)
    assert sources is not None
    tools = await sources.get_tools(ctx)
    await sources.call_tool(
        "research_literature_search",
        {"query": "ROP18 kinase"},
        ctx,
        tools["research_literature_search"],
    )


def _a_pass_that_reads_a_paper(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(**kwargs: Any) -> FrameResult:
        await _read_a_paper(kwargs["agent_deps"])
        return FrameResult(disposition="needs_user", summary="which dataset?")

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)


def _turn(capture: _LeadRunCapture) -> LeadDeps:
    deps = lead_deps(pipeline_state(user_prompt="what does ROP18 do?"))
    deps.runtime = replace(deps.runtime, tool_sources={"research": _served_research()})
    _, record_tool = usage_recorders(capture, deps.state, ChunkCollector())
    deps.record_tool_charge = record_tool
    return deps


async def _dispatch(deps: LeadDeps) -> None:
    await run_frame(
        deps=deps,
        parent_tool_call_id="t1",
        work_order=frame_work_order("frame it", deps.state),
    )


async def test_a_paper_a_sub_agent_read_is_on_the_turns_markers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _a_pass_that_reads_a_paper(monkeypatch)
    capture = _LeadRunCapture()
    deps = _turn(capture)

    await _dispatch(deps)

    assert deps.state.turn_markers.retrieved_sources == [_DOI]


async def test_a_priced_search_a_sub_agent_made_is_on_the_turns_bill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _a_pass_that_reads_a_paper(monkeypatch)
    capture = _LeadRunCapture()
    deps = _turn(capture)

    await _dispatch(deps)

    assert capture.tool_cost == _PRICE


async def test_the_lead_may_cite_what_a_sub_agent_retrieved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The turn contract reads one record, so a sub-agent's read clears a citation."""
    _a_pass_that_reads_a_paper(monkeypatch)
    capture = _LeadRunCapture()
    deps = _turn(capture)
    await _dispatch(deps)
    reply = LeadResponse(
        prose="ROP18 is a rhoptry kinase.",
        strategy_changed=False,
        sources=[
            CitedSource(kind="literature", label="ROP18 is a rhoptry kinase", doi=_DOI),
        ],
    )

    held = hold_the_turn_contract(run_context_for(deps), reply)

    assert held is reply
    assert deps.state.turn_markers.contract_refused is False
