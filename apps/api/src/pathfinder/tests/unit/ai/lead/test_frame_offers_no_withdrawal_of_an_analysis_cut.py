"""A significance cut and a fold requirement that a waiting analysis states are
never offered for withdrawal: the analysis has not run, so nothing fails to
state them."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from veupathdb.domain.parameters import StringValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import Withdraw
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)
from pathfinder.tests.unit.domain.strategy._analysis import pending

_REQUEST = "At p 0.001 with no fold change cutoff, how many genes pass?"
_P = requirement(ConstraintKind.STATISTICAL_THRESHOLD, "p-value cutoff", "p 0.001")
_NO_FOLD = requirement(
    ConstraintKind.FOLD_CHANGE, "fold change", "no fold change cutoff"
)
_ORTHOLOGS = Criterion(
    id="c_orthologs",
    text="with orthologs in Aspergillus",
    search_name="GenesOrthologousToAGivenOrganism",
    resolved_params={
        "organism": BoundValue(value=StringValue(value="Aspergillus"), source="stated")
    },
)


@pytest.mark.asyncio
async def test_the_card_offers_no_withdrawal_of_a_cut_the_analysis_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake(**kwargs: Any) -> FrameResult:
        draft = kwargs["agent_deps"].agent_state.operational_spec_draft
        draft.goal = _REQUEST
        draft.criteria = [pending(), _ORTHOLOGS]
        return FrameResult(disposition="spec_ready", summary="waits for the analysis")

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)
    deps = lead_deps(
        pipeline_state(
            "fungidb",
            user_prompt=_REQUEST,
            user_message_id=uuid4(),
            domain=StrategyDomainState(
                requirements=[_P, _NO_FOLD],
                operational_spec=OperationalSpec(goal=_REQUEST),
            ),
        )
    )

    result = await run_frame(
        deps=deps, parent_tool_call_id="t1", work_order=frame_work_order("go", deps)
    )

    assert isinstance(result, FrameResult)
    assert [
        o.binding
        for q in deps.state.domain.open_questions
        for o in q.options
        if isinstance(o.binding, Withdraw)
    ] == []
    assert result.card_questions == []
