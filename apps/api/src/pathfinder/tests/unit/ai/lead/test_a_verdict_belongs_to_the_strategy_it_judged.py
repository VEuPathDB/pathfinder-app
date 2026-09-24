"""A verification verdict stands while the strategy holds the revision it judged."""

from __future__ import annotations

from uuid import uuid4

from assistant_core.memory.schemas import MemoryEntryDraft
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.graph.state import PipelineState, VerificationDigest
from pathfinder.ai.lead.answered_strategy import live_tree
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.memory_candidates import collect_memory_candidates
from pathfinder.ai.lead.turn_budget import budget_stop_report
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests.unit.ai.lead._budget_stop_turn import (
    BUDGET,
    NOT_VERIFIED,
    SEARCH,
    STEP,
    STRATEGY_LINE,
    TITLE,
    built_outcome,
    built_session,
    objection,
)
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state, user_intent

_FINDING = MemoryEntryDraft(
    name="Aedes 24 h responders", summary="70 genes", content={"genes": 70}
)
_PASSED = objection().model_copy(update={"success": True, "remember": [_FINDING]})
_VERIFIED = "## Verification\n- complete: True\n- successful: True"


def _answered_the(state: PipelineState, session: StrategySession) -> None:
    """Record the live tree as the one the thread answers to."""
    state.domain.answered_graph = live_tree(session.get_graph(None))


def _judged(state: PipelineState, digest: VerificationDigest) -> None:
    """Record a check of the tree the thread answers to."""
    state.domain.record_verdict(
        digest, revision=strategy_revision(state.domain.answered_graph)
    )


def _verified() -> tuple[PipelineState, StrategySession]:
    """An earlier message built one step and its check passed."""
    session = built_session()
    state = pipeline_state(user_prompt="find the 24 h responders")
    state.user_message_id = uuid4()
    state.record_build(built_outcome())
    _answered_the(state, session)
    state.turn_markers.verification_dispatched = True
    _judged(state, _PASSED)
    state.turn_markers.verified = True
    return state, session


def _next_message(state: PipelineState, prompt: str) -> None:
    state.user_message_id = uuid4()
    state.user_prompt = prompt


def _edited() -> tuple[PipelineState, StrategySession]:
    """The next message sets a parameter on the step the check judged."""
    state, session = _verified()
    _next_message(state, "use 18 h only")
    graph = session.get_graph(None)
    assert graph is not None
    graph.steps = flatten_tree(
        StrategyStepNode(
            id=STEP,
            search_name=SEARCH,
            display_name=TITLE,
            parameters={"reference": StringValue(value="18 h")},
        )
    )
    graph.recompute_roots()
    _answered_the(state, session)
    state.turn_markers.edited = True
    return state, session


def test_a_question_after_a_verified_build_keeps_the_verdict() -> None:
    state, _ = _verified()
    _next_message(state, "What does PF3D7_1133400 do?")

    ledger = derive_ledger(state, user_intent(IntentClassification.FOLLOW_UP_QUESTION))

    assert (ledger.verification.complete, ledger.verification.successful) == (
        True,
        True,
    )
    assert _VERIFIED in ledger.render_summary()


def test_a_resumed_turn_and_a_completion_turn_keep_the_verdict() -> None:
    """A resumed turn keeps the message id; a completion turn may carry another."""
    state, _ = _verified()
    assert state.turn_verdict == _PASSED

    state.user_message_id = uuid4()

    assert state.turn_verdict == _PASSED


def test_an_edit_that_changes_the_strategy_blanks_the_verdict() -> None:
    state, _ = _edited()

    summary = derive_ledger(state, None).render_summary()

    assert summary.split("## Verification\n")[1].split("\n\n")[0] == (
        "- complete: False\n- successful: False"
    )


def test_a_budget_stop_after_an_edit_reports_no_earlier_verdict() -> None:
    state, session = _edited()

    report = budget_stop_report(
        derive_ledger(state, None), session, state.turn_markers, []
    )

    assert report == "\n\n".join(
        [
            STRATEGY_LINE,
            "This turn changed the strategy and added no step.",
            NOT_VERIFIED,
            BUDGET,
        ]
    )


def test_an_earlier_verdict_writes_no_finding_after_an_edit() -> None:
    state, _ = _edited()

    keys = [key for _, key in collect_memory_candidates(state)]

    assert [key for key in keys if key.startswith("knowledge:")] == []


def test_the_check_of_the_edited_strategy_is_the_verdict() -> None:
    state, _ = _edited()
    state.turn_markers.verification_dispatched = True

    _judged(state, objection())

    ledger = derive_ledger(state, None)
    assert ledger.verification.digest == objection()
    assert (
        "## Verification\n- complete: True\n- successful: False"
        in ledger.render_summary()
    )
