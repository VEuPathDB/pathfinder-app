"""The withdraw arc's turn: a fold change no search of the spec states is
offered for withdrawal on the card, and once the researcher drops it the facts
part shows it retired and no gap names it."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import PendingApproval, UserQuestionAnswer
from veupathdb.domain.parameters import MultiPickValue

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead import frame_dispatch
from strategist.ai.lead.deltas import FrameResult
from strategist.ai.lead.frame_dispatch import frame_work_order, run_frame
from strategist.ai.lead.lead_consult import consult_user
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.lead.turn_facts import turn_facts
from strategist.domain.strategy.constraints import ConstraintKind
from strategist.domain.strategy.operational_spec import BoundValue, Criterion
from strategist.domain.turn_facts import RetiredFact
from strategist.tests._support.run_context import run_context_for
from strategist.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_FOLD = requirement(ConstraintKind.FOLD_CHANGE, "fold change", "2-fold")
_DROP = "Drop 2-fold"


def _deps(monkeypatch: pytest.MonkeyPatch) -> LeadDeps:
    async def _signal_peptide(**kwargs: Any) -> FrameResult:
        draft = kwargs["agent_deps"].agent_state.operational_spec_draft
        draft.criteria.append(
            Criterion(
                id="c_signal",
                text="with a signal peptide",
                search_name="GenesWithSignalPeptide",
                resolved_params={
                    "organism": BoundValue(
                        value=MultiPickValue(values=["Plasmodium falciparum 3D7"]),
                        source="stated",
                    )
                },
                result_count=1033,
            )
        )
        return FrameResult(disposition="spec_ready", summary="signal peptide bound")

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _signal_peptide)
    return lead_deps(
        pipeline_state(
            "plasmodb",
            user_prompt="Genes with a signal peptide, up at least 2-fold",
            user_message_id=uuid4(),
            domain=StrategyDomainState(requirements=[_FOLD]),
        )
    )


@pytest.mark.asyncio
async def test_the_dropped_fold_change_is_retired_and_no_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(monkeypatch)
    framed = await run_frame(
        deps=deps, parent_tool_call_id="t1", work_order=frame_work_order("go", deps)
    )
    assert isinstance(framed, FrameResult)
    [card] = framed.card_questions
    assert [o.label for o in card.options] == [_DROP, "Keep 2-fold"]
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(
                question_id=card.id, prompt=card.prompt, chosen_labels=[_DROP]
            )
        ]
    }

    await consult_user(
        run_context_for(deps, "call_card"), questions=[card], reply="One question."
    )

    facts = turn_facts(deps)
    assert [r for r in facts.retired if r.state == "withdrawn"] == [
        RetiredFact(requirement="2-fold", state="withdrawn")
    ]
    assert [gap.sentence for gap in facts.gaps if "2-fold" in gap.sentence] == []
