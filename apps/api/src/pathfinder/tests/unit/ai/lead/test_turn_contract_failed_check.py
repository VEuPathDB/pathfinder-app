"""A reply over a standing check that failed states the failure or asks."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry

from pathfinder.ai.agents.refusal_bound import REFUSALS_PER_CHECK
from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import hold_the_turn_contract, reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.caveats import Gap, RequirementGap
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.questions import AskedQuestion
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    kinds,
    reading_deps,
    reply,
)

# The vectorbase check: seven of eight sampled genes are not OBPs.
_REASON = "Seven of eight sampled genes are not odorant-binding proteins."
_BUILT = "The strategy returns 8 gene records on chromosome 3."


def _failed(*, gaps: list[Gap], success: bool = False) -> LeadDeps:
    deps = reading_deps()
    domain = deps.state.domain
    domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="Checked.",
            reason=_REASON,
            success=success,
            gaps=gaps,
        ),
        revision=strategy_revision(domain.answered_graph),
    )
    return deps


_OBP_GAP = RequirementGap(text="odorant-binding protein", status="unmet")


def test_a_reply_that_hides_a_failed_check_is_refused() -> None:
    assert "failed_check" in kinds(_failed(gaps=[_OBP_GAP]), reply(_BUILT))


def test_a_reply_that_names_each_gap_stands() -> None:
    prose = (
        f"{_BUILT} The check found the odorant-binding protein requirement is "
        "not answered: most sampled genes are kinases."
    )

    assert "failed_check" not in kinds(_failed(gaps=[_OBP_GAP]), reply(prose))


def test_a_reply_that_asks_how_to_go_on_stands() -> None:
    question = AskedQuestion(
        question="Should the OBP search read the product text instead?",
        dimension=ConstraintKind.OTHER,
        recommended_value="the product text",
    )

    assert "failed_check" not in kinds(
        _failed(gaps=[_OBP_GAP]), reply(_BUILT, questions=[question])
    )


def test_a_failure_with_no_gap_is_stated_by_its_reason() -> None:
    deps = _failed(gaps=[])

    assert (
        "failed_check" in kinds(deps, reply(_BUILT)),
        "failed_check" in kinds(deps, reply(f"{_BUILT} {_REASON}")),
    ) == (True, False)


def test_a_passed_check_asks_nothing() -> None:
    assert "failed_check" not in kinds(_failed(gaps=[], success=True), reply(_BUILT))


def test_a_gap_is_named_by_its_words_and_never_by_its_number() -> None:
    """A reply carries no number, so a gap with one is named by its other words."""
    tm_gap = RequirementGap(text="at least 2 transmembrane domains", status="unmet")
    deps = _failed(gaps=[tm_gap])

    assert (
        "failed_check" in kinds(deps, reply("The strategy has no TM step yet.")),
        "failed_check"
        in kinds(deps, reply("It does not yet require the transmembrane domains.")),
    ) == (True, False)


def test_the_refusal_names_each_gap_the_reply_must_state() -> None:
    deps = _failed(gaps=[_OBP_GAP])

    [sentence] = [
        m.sentence
        for m in reconcile(reply(_BUILT), turn_record(run_context_for(deps)))
        if m.kind == "failed_check"
    ]

    assert sentence == (
        f"The last check of this strategy failed: {_REASON} Nothing has changed "
        "since, so the reply states that verdict: name each requirement it found "
        "unanswered, 'odorant-binding protein'. Or ask the researcher how to go "
        "on, recorded in ``asked_questions`` or on a card."
    )


def test_the_refusal_of_a_failure_with_no_gap_asks_for_its_reason() -> None:
    deps = _failed(gaps=[])

    [sentence] = [
        m.sentence
        for m in reconcile(reply(_BUILT), turn_record(run_context_for(deps)))
        if m.kind == "failed_check"
    ]

    assert "the reply states that verdict: quote its reason." in sentence


_UNJUDGED = RequirementGap(text="signal peptide", status="unjudged")


def test_an_unjudged_gap_is_not_asked_for() -> None:
    deps = _failed(gaps=[_UNJUDGED, _OBP_GAP])

    [sentence] = [
        m.sentence
        for m in reconcile(reply(_BUILT), turn_record(run_context_for(deps)))
        if m.kind == "failed_check"
    ]

    assert "name each requirement it found unanswered, 'odorant-binding protein'." in (
        sentence
    )
    assert "signal peptide" not in sentence


def test_with_only_an_unjudged_gap_the_reply_states_the_reason() -> None:
    deps = _failed(gaps=[_UNJUDGED])

    assert (
        "failed_check" in kinds(deps, reply(_BUILT)),
        "failed_check" in kinds(deps, reply(f"{_BUILT} {_REASON}")),
    ) == (True, False)


_PLAIN = "The strategy returns the gene records of the search."


def test_past_the_budget_a_hidden_failed_check_marks_the_reply_unchecked() -> None:
    deps = _failed(gaps=[_OBP_GAP])
    deps.state.turn_markers.output_refusals = REFUSALS_PER_CHECK
    answer = reply(_PLAIN)

    assert hold_the_turn_contract(run_context_for(deps), answer) == answer
    assert deps.state.turn_markers.unchecked_reply is True


def test_a_second_answer_that_still_hides_the_failure_is_marked_unchecked() -> None:
    deps = _failed(gaps=[_OBP_GAP])
    ctx = run_context_for(deps)
    with pytest.raises(ModelRetry):
        hold_the_turn_contract(ctx, reply(_PLAIN))

    assert hold_the_turn_contract(ctx, reply(_PLAIN)) == reply(_PLAIN)
    assert deps.state.turn_markers.unchecked_reply is True


def test_past_the_budget_a_claimed_change_states_the_change_the_record_holds() -> None:
    deps = _failed(gaps=[], success=True)
    deps.state.turn_markers.output_refusals = REFUSALS_PER_CHECK

    let_through = hold_the_turn_contract(
        run_context_for(deps), reply(_PLAIN, changed=True)
    )

    assert let_through == reply(_PLAIN, changed=False)
    assert deps.state.turn_markers.unchecked_reply is False
