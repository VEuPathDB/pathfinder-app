"""A proposal card over a built strategy: a yes pushes the changes it names
through the edit path, and a no leaves the strategy as the offer found it."""

from __future__ import annotations

from typing import Any

import pytest
from assistant_core.graph.turn_state import PendingApproval, UserQuestionAnswer
from pydantic_ai.ui.vercel_ai.request_types import ToolApprovalResponded
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_stops import final_reply
from pathfinder.ai.graph._lead_turn import (
    resolve_turn_resumption,
    turn_ends_before_the_run,
)
from pathfinder.ai.lead import lead_proposal
from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.lead_proposal import propose_changes
from pathfinder.ai.lead.proposal import PROPOSAL_TOOL, DeclinedProposal, Proposal
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    structure_criteria,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    PROTEOME,
    with_the_proteome,
)
from pathfinder.tests.unit.ai.lead._disagreement_facts import committed_facts
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    ROOT,
    STAGE,
    SURFACE,
    DisagreementThread,
    Draft,
    built_spec,
    built_tree,
    joined,
    kept,
    leaf,
    recorded,
    session_holding,
)

CALL_ID = "call_propose"
SPECIFIC = "c_specific_at_3h"
THE_CARD = Proposal(
    question="Refine the strategy with the two checks verification asked for?",
    proposed_changes=[
        "Require detection in the merozoite proteome",
        "Exclude genes highly expressed at the other time points",
    ],
)


def _thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    thread = DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )
    monkeypatch.setattr(lead_proposal, "get_stream_writer", lambda: lambda _p: None)
    thread.deps.state.pending_approval = PendingApproval(
        phase="lead",
        tool_call_id=CALL_ID,
        tool_name=PROPOSAL_TOOL,
        tool_args=THE_CARD.model_dump(by_alias=True),
        user_message_id=thread.deps.state.user_message_id,
    )
    return thread


def _with_both_refinements() -> Draft:
    """The workspace plus the two criteria the card names, at the root."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        found = with_the_proteome(2)(found)
        found.criteria.append(
            Criterion(
                id=SPECIFIC,
                text="not highly expressed at the other time points",
                search_name="GenesByRNASeqEvidence",
                resolved_params={"max_percentile": NumberValue(value=20)},
            )
        )
        assert found.structure is not None
        if SPECIFIC not in structure_criteria(found.structure):
            found.structure = SpecStructure(
                root=joined(CombineOp.INTERSECT, found.structure.root, leaf(SPECIFIC))
            )
        return found

    return _draft


async def test_yes_builds_the_two_refinements_the_card_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    thread.deps.state.user_question_answers = {
        CALL_ID: [
            UserQuestionAnswer(
                question_id="proposal",
                prompt=THE_CARD.question,
                chosen_labels=["Yes"],
                note="Keep the surface filter as it is.",
            )
        ],
    }
    thread.frames(_with_both_refinements(), declared=kept(SURFACE, STAGE))

    delta = await propose_changes(run_context_for(thread.deps, CALL_ID), THE_CARD)

    assert isinstance(delta, EditDelta)
    assert delta.diff.added_count == 2
    assert sorted(delta.added_step_ids) == sorted([PROTEOME, SPECIFIC])
    added = [
        op.step_id for op in committed_facts(thread.committed) if op.kind == "addLeaf"
    ]
    assert sorted(added) == sorted([PROTEOME, SPECIFIC])
    assert {PROTEOME, SPECIFIC} <= set(thread.graph.steps)
    assert thread.deps.state.turn_markers.accepted_proposal is True
    thread.assert_invariants()


async def test_no_leaves_the_strategy_and_the_reply_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    before = thread.facts()
    state = thread.deps.state
    state.approval_responses = {
        CALL_ID: ToolApprovalResponded(id=CALL_ID, approved=False),
    }
    written: list[dict[str, Any]] = []
    capture = _LeadRunCapture()

    resumption = await resolve_turn_resumption(state=state, deps=thread.deps)
    ended = turn_ends_before_the_run(resumption, capture, written.append)

    assert ended is True
    assert thread.committed == []
    assert thread.facts() == before
    assert final_reply(capture, None, changed=False) is None
    assert [p["chunk"]["type"] for p in written] == [
        "tool-input-start",
        "tool-input-available",
        "tool-output-denied",
    ]
    assert state.domain.declined_proposal == DeclinedProposal(
        question=THE_CARD.question, proposed_changes=THE_CARD.proposed_changes
    )
