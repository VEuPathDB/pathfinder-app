from __future__ import annotations

from typing import Any

import pytest

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.named_groups import GroupScope
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_WHOLE = GroupScope(taxon="Plasmodium", scope="whole", except_codes=["pber"])
_NAMED = GroupScope(taxon="Cryptosporidium", scope="named")


def _deps() -> LeadDeps:
    return lead_deps(pipeline_state("orthomcl", user_prompt="groups in plasmodia"))


def _passes(monkeypatch: pytest.MonkeyPatch, results: list[FrameResult]) -> None:
    async def _fake(**kwargs: Any) -> FrameResult:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        agent_deps.agent_state.operational_spec_draft.criteria.append(
            Criterion(id=f"c{len(results)}", text="groups", search_name="ByText")
        )
        return results.pop(0)

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)


async def test_a_later_pass_keeps_the_scopes_an_earlier_pass_stated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _passes(
        monkeypatch,
        [
            FrameResult(summary="bound one", group_scopes=[_WHOLE]),
            FrameResult(summary="bound two", group_scopes=[_NAMED]),
            FrameResult(summary="bound three"),
        ],
    )
    deps = _deps()

    for _ in range(3):
        await run_frame(
            deps=deps,
            parent_tool_call_id="t1",
            work_order=frame_work_order("frame it", deps),
        )

    assert deps.state.domain.group_scopes == {
        "plasmodium": _WHOLE,
        "cryptosporidium": _NAMED,
    }


def test_a_pass_starts_from_the_scopes_the_thread_holds() -> None:
    deps = _deps()
    deps.state.domain.group_scopes = {"plasmodium": _WHOLE}

    assert agent_deps_for(deps, call_id="call_test").agent_state.held_group_scopes == {
        "plasmodium": _WHOLE
    }


def test_a_new_request_over_an_empty_strategy_forgets_the_scopes() -> None:
    deps = _deps()
    deps.state.domain.group_scopes = {"plasmodium": _WHOLE}

    deps.state.domain.take_a_new_request(strategy_has_steps=False)

    assert deps.state.domain.group_scopes == {}
