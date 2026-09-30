"""A requirement the researcher stated that no search states is offered for
withdrawal on the card FRAME leaves, beside the values the nearest search offers,
and a withdrawal answered on that card leaves the ledger with no such row."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import PendingApproval, UserQuestionAnswer
from veupathdb.domain.parameters import StringValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.lead_consult import consult_user
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import ConstraintKind, ConstraintStatus
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    DroppedCriterion,
    OpenSlot,
)
from pathfinder.domain.strategy.questions import (
    Keep,
    SetValues,
    SlotQuestion,
    Withdraw,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_CUTOFF = requirement(
    ConstraintKind.PERCENTILE, "expression", "top 50th percentile in bradyzoites"
)
_FLOOR = "min_expression_percentile"
_TACHYZOITE = "GenesByRNASeqtgonME49_Tachyzoite_RSRCPercentile"
_NEAREST = SlotQuestion(
    question="No bradyzoite study ranks expression. Use the tachyzoite floor?",
    dimension=ConstraintKind.PERCENTILE,
    recommended_value="50",
    criterion_id="c_tachy",
    param_name=_FLOOR,
    options=["50", "75"],
)


def _deps(monkeypatch: pytest.MonkeyPatch, *asked: SlotQuestion) -> LeadDeps:
    """A pass that binds the signal peptide step and drops the bradyzoite floor."""

    async def _fake(**kwargs: Any) -> FrameResult:
        draft = kwargs["agent_deps"].agent_state.operational_spec_draft
        draft.criteria.append(
            Criterion(
                id="c_signal",
                text="with a signal peptide",
                search_name="GenesWithSignalPeptide",
                resolved_params={
                    "organism": BoundValue(
                        value=StringValue(value="Toxoplasma gondii ME49"),
                        source="stated",
                    )
                },
                result_count=1033,
            )
        )
        if asked:
            draft.criteria.append(
                Criterion(
                    id="c_tachy",
                    text="expressed in tachyzoites",
                    search_name=_TACHYZOITE,
                    param_display_names={_FLOOR: "Minimum expression percentile"},
                    open_params=[OpenSlot(criterion_id="c_tachy", param_name=_FLOOR)],
                )
            )
        draft.dropped.append(
            DroppedCriterion(
                text="top 50th percentile in bradyzoites",
                reason="no search ranks bradyzoite expression",
                requirement=_CUTOFF,
            )
        )
        return FrameResult(
            disposition="needs_user",
            summary="no bradyzoite percentile search",
            open_questions=list(asked),
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)
    return lead_deps(
        pipeline_state(
            "toxodb",
            user_prompt=(
                "Toxoplasma genes with a signal peptide, top 50th percentile in "
                "bradyzoites"
            ),
            user_message_id=uuid4(),
            domain=StrategyDomainState(requirements=[_CUTOFF]),
        )
    )


async def _framed(deps: LeadDeps) -> FrameResult:
    result = await run_frame(
        deps=deps, parent_tool_call_id="t1", work_order=frame_work_order("go", deps)
    )
    assert isinstance(result, FrameResult)
    return result


@pytest.mark.asyncio
async def test_the_ledger_lists_the_dropped_requirement_as_ungroundable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(monkeypatch)
    await _framed(deps)

    rows = derive_ledger(deps.state, deps.intent).constraints.grounded
    assert [
        g.constraint.key for g in rows if g.status is ConstraintStatus.UNGROUNDABLE
    ] == ["percentile:top 50th percentile in bradyzoites"]


@pytest.mark.asyncio
async def test_a_requirement_no_question_asks_gets_a_question_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(monkeypatch)

    result = await _framed(deps)

    [asked] = deps.state.domain.open_questions
    assert asked.question == (
        "No search on this site states 'top 50th percentile in bradyzoites'. "
        "Drop it from the request?"
    )
    assert [(o.label, o.binding) for o in asked.options] == [
        (
            "Drop top 50th percentile in bradyzoites",
            Withdraw(constraint_id="percentile:top 50th percentile in bradyzoites"),
        ),
        (
            "Keep top 50th percentile in bradyzoites",
            Keep(constraint_id="percentile:top 50th percentile in bradyzoites"),
        ),
    ]
    assert [o.label for q in result.card_questions for o in q.options] == [
        "Drop top 50th percentile in bradyzoites",
        "Keep top 50th percentile in bradyzoites",
    ]


@pytest.mark.asyncio
async def test_the_withdrawal_joins_the_nearest_searchs_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(monkeypatch, _NEAREST)

    await _framed(deps)

    [asked] = deps.state.domain.open_questions
    assert [(o.label, o.binding) for o in asked.options] == [
        (
            "Minimum expression percentile 50",
            SetValues(criterion_id="c_tachy", params={_FLOOR: "50"}),
        ),
        (
            "Minimum expression percentile 75",
            SetValues(criterion_id="c_tachy", params={_FLOOR: "75"}),
        ),
        (
            "Drop top 50th percentile in bradyzoites",
            Withdraw(constraint_id="percentile:top 50th percentile in bradyzoites"),
        ),
    ]


@pytest.mark.asyncio
async def test_a_withdrawal_on_the_card_leaves_no_ungroundable_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(monkeypatch)
    result = await _framed(deps)
    [card] = result.card_questions
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(
                question_id=card.id,
                prompt=card.prompt,
                chosen_labels=["Drop top 50th percentile in bradyzoites"],
            )
        ]
    }

    await consult_user(
        run_context_for(deps, "call_card"), questions=[card], reply="One question."
    )

    rows = derive_ledger(deps.state, deps.intent).constraints.grounded
    assert deps.state.domain.requirements == []
    assert [g.constraint.key for g in rows if not g.retired] == []
    assert not derive_ledger(deps.state, deps.intent).constraints.blocking
