from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead import frame_dispatch
from strategist.ai.lead.deltas import FrameResult
from strategist.ai.lead.derive import derive_ledger
from strategist.ai.lead.frame_dispatch import frame_work_order, run_frame
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.domain.strategy.constraints import Constraint, ConstraintStatus
from strategist.domain.strategy.operational_spec import OperationalSpec
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_B1 = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "turns"
        / "b1_pexel_rna_seq_frame.json"
    ).read_text()
)
_SPEC = OperationalSpec.model_validate(_B1["spec"])
_REQUIREMENTS = [Constraint.model_validate(c) for c in _B1["requirements"]]
_R5 = "739b3956e59e"


def _deps(monkeypatch: pytest.MonkeyPatch) -> LeadDeps:
    async def _fake(**kwargs: Any) -> FrameResult:
        draft = kwargs["agent_deps"].agent_state.operational_spec_draft
        draft.criteria.extend(_SPEC.criteria)
        draft.structure = _SPEC.structure
        return FrameResult(disposition="spec_ready", summary="framed")

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)
    return lead_deps(
        pipeline_state(
            "plasmodb",
            user_prompt=_SPEC.goal,
            user_message_id=uuid4(),
            domain=StrategyDomainState(requirements=list(_REQUIREMENTS)),
        )
    )


@pytest.mark.asyncio
async def test_frame_grounds_the_data_type_its_spec_runs_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(monkeypatch)

    result = await run_frame(
        deps=deps,
        parent_tool_call_id="t1",
        work_order=frame_work_order(_SPEC.goal, deps),
    )

    assert isinstance(result, FrameResult)
    [r5] = [
        g
        for g in derive_ledger(deps.state, deps.intent).constraints.grounded
        if g.constraint.id == _R5
    ]
    assert (result.card_questions, r5.status, r5.realized_value) == (
        [],
        ConstraintStatus.GROUNDED,
        "rna_seq",
    )
