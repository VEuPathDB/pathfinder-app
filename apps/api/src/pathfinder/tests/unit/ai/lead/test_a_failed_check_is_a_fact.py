from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.caveats import Gap
from pathfinder.domain.site_checks import SiteCheck, SiteCheckGap
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reading_deps

_REASON = "Seven of eight sampled genes are not odorant-binding proteins."


def _checked(
    *, success: bool, reason: str = _REASON, gaps: list[Gap] | None = None
) -> LeadDeps:
    deps = reading_deps()
    domain = deps.state.domain
    domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="Checked.",
            reason=reason,
            success=success,
            gaps=gaps or [],
        ),
        revision=strategy_revision(domain.answered_graph),
    )
    return deps


def test_a_failed_check_is_shown_with_its_reason() -> None:
    facts = turn_facts(_checked(success=False))

    assert facts.failed_check == f"The last check of this strategy failed: {_REASON}"


def test_a_failure_with_no_reason_is_shown_as_failed() -> None:
    facts = turn_facts(_checked(success=False, reason=""))

    assert facts.failed_check == "The last check of this strategy failed."


def test_a_passed_check_shows_no_failure() -> None:
    assert turn_facts(_checked(success=True)).failed_check == ""


def test_a_failed_check_alone_makes_a_facts_part() -> None:
    facts = turn_facts(_checked(success=False))

    assert facts.model_copy(update={"steps": [], "gaps": []}).empty() is False


def test_a_failure_its_gap_states_is_not_stated_twice() -> None:
    gap = SiteCheckGap(
        check=SiteCheck(
            kind=ConstraintKind.ORGANISM,
            subject="Plasmodium species",
            status="fail",
            evidence="no step restricts the groups to Plasmodium",
            requirement="organism",
        )
    )
    facts = turn_facts(_checked(success=False, reason=gap.sentence, gaps=[gap]))

    assert (facts.failed_check, [g.sentence for g in facts.gaps]) == (
        "The last check of this strategy failed.",
        [gap.sentence],
    )
