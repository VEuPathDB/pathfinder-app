"""A reply over a standing check that failed states the failure or asks."""

from __future__ import annotations

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.caveats import Gap, RequirementGap
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.questions import AskedQuestion
from pathfinder.domain.strategy.revision import strategy_revision
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
