"""The organism a request runs in is never offered for withdrawal because a
pass names the whole request as unstated, and a question the pass wrote keeps
its prompt and takes an answer in the researcher's words beside drop and keep."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import PendingApproval, UserQuestionAnswer

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.lead_consult import consult_user
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.questions import Keep, SlotQuestion, Withdraw
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_REQUEST = "Find P. falciparum 3D7 genes with a predicted GPI anchor"
_ORGANISM = requirement(ConstraintKind.ORGANISM, "organism", "P. falciparum 3D7")
_GPI = requirement(ConstraintKind.OTHER, "predicted GPI anchor", "predicted GPI anchor")
_SUBSTITUTE = SlotQuestion(
    question=(
        "VEuPathDB does not provide a predicted GPI-anchor search. Should I "
        "substitute the nearest available predicted signal-peptide search, or "
        "the predicted exported-protein search?"
    ),
    dimension=ConstraintKind.DATA_TYPE,
    recommended_value="Predicted Signal Peptide",
    options=["Predicted Signal Peptide", "Exported Protein"],
    criterion_id="c_predicted_gpi_anchor",
)


def _deps(monkeypatch: pytest.MonkeyPatch) -> LeadDeps:
    """A pass that binds nothing and names the whole request as unstated."""

    async def _fake(**kwargs: Any) -> FrameResult:
        kwargs["agent_deps"].agent_state.operational_spec_draft.goal = _REQUEST
        return FrameResult(
            disposition="needs_user",
            summary="no search states a predicted GPI anchor",
            open_questions=[_SUBSTITUTE],
            unstated=[_REQUEST],
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)
    deps = lead_deps(
        pipeline_state(
            "plasmodb",
            user_prompt=_REQUEST,
            user_message_id=uuid4(),
            domain=StrategyDomainState(
                requirements=[_ORGANISM, _GPI],
                operational_spec=OperationalSpec(goal=_REQUEST),
            ),
        )
    )
    # The pass was refused once for its unbound question and asked it again.
    deps.unbound_questions_reported = True
    return deps


async def _framed(deps: LeadDeps) -> FrameResult:
    result = await run_frame(
        deps=deps, parent_tool_call_id="t1", work_order=frame_work_order("go", deps)
    )
    assert isinstance(result, FrameResult)
    return result


@pytest.mark.asyncio
async def test_the_card_asks_about_the_gpi_anchor_and_not_the_organism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(monkeypatch)

    result = await _framed(deps)

    [asked] = deps.state.domain.open_questions
    assert asked.question == _SUBSTITUTE.question
    assert [(o.label, o.binding) for o in asked.options] == [
        ("Drop predicted GPI anchor", Withdraw(constraint_id=_GPI.key)),
        ("Keep predicted GPI anchor", Keep(constraint_id=_GPI.key)),
    ]
    assert [q.prompt for q in result.card_questions] == [_SUBSTITUTE.question]


@pytest.mark.asyncio
async def test_a_substitute_named_in_words_is_recorded_and_the_organism_stays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(monkeypatch)
    [card] = (await _framed(deps)).card_questions
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(
                question_id=card.id,
                prompt=card.prompt,
                chosen_labels=["Drop predicted GPI anchor"],
                note="Predicted Signal Peptide",
            )
        ]
    }

    await consult_user(
        run_context_for(deps, "call_card"), questions=[card], reply="One question."
    )

    assert [(c.kind, c.requested_value) for c in deps.state.domain.requirements] == [
        (ConstraintKind.ORGANISM, "P. falciparum 3D7"),
        (ConstraintKind.DATA_TYPE, "Predicted Signal Peptide"),
    ]
