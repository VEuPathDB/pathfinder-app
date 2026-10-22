from __future__ import annotations

from typing import Any

import pytest

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.requirement_reports import (
    RecordTypeRole,
    record_roles,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_PROTEINS = requirement(ConstraintKind.RECORD_TYPE, "record type", "protein")
_GROUPS = requirement(ConstraintKind.RECORD_TYPE, "record type", "ortholog group")
_ORGANISM = requirement(ConstraintKind.ORGANISM, "organism", "P. falciparum 3D7")


def _deps() -> LeadDeps:
    deps = lead_deps(pipeline_state("orthomcl", user_prompt="groups of kinases"))
    deps.state.domain.requirements = [_PROTEINS, _GROUPS]
    return deps


def _passes(monkeypatch: pytest.MonkeyPatch, results: list[FrameResult]) -> None:
    async def _fake(**kwargs: Any) -> FrameResult:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        agent_deps.agent_state.operational_spec_draft.criteria.append(
            Criterion(id=f"c{len(results)}", text="kinases", search_name="ByText")
        )
        return results.pop(0)

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)


async def _frame(deps: LeadDeps) -> None:
    await run_frame(
        deps=deps,
        parent_tool_call_id="t1",
        work_order=frame_work_order("frame it", deps),
    )


async def test_a_later_pass_keeps_the_roles_an_earlier_pass_stated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _passes(
        monkeypatch,
        [
            FrameResult(
                summary="bound one",
                record_types=[RecordTypeRole(requirement="R1", role="through")],
            ),
            FrameResult(
                summary="bound two",
                record_types=[RecordTypeRole(requirement="R2", role="answer")],
            ),
            FrameResult(summary="bound three"),
        ],
    )
    deps = _deps()

    for _ in range(3):
        await _frame(deps)

    assert deps.state.domain.record_roles == {
        _PROTEINS.key: "through",
        _GROUPS.key: "answer",
    }


def test_a_new_request_over_an_empty_strategy_forgets_the_roles() -> None:
    deps = _deps()
    deps.state.domain.record_roles = {_PROTEINS.key: "through"}

    deps.state.domain.take_a_new_request(strategy_has_steps=False)

    assert deps.state.domain.record_roles == {}


def test_a_role_named_for_a_requirement_that_is_no_record_type_is_ignored() -> None:
    stated = [
        RecordTypeRole(requirement="R1", role="through"),
        RecordTypeRole(requirement="R2", role="answer"),
    ]

    assert record_roles(stated, [_ORGANISM, _GROUPS]) == {_GROUPS.key: "answer"}


def test_a_pass_starts_from_the_roles_the_thread_holds() -> None:
    deps = _deps()
    deps.state.domain.record_roles = {_PROTEINS.key: "through"}

    held = agent_deps_for(deps).agent_state.held_record_roles

    assert held == {_PROTEINS.key: "through"}
