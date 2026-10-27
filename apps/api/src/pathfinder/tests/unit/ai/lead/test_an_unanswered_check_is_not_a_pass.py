from __future__ import annotations

from pydantic_ai.messages import ToolReturnPart

from pathfinder.ai.graph._lead_events import _summarize_sub_agent_result
from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead import turn_budget
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.ledger_render import render_verification_full
from pathfinder.ai.lead.ledger_sections import VerificationSection
from pathfinder.domain.evidence import VerificationReview
from pathfinder.domain.site_checks import SiteCheck, unanswered_checks

_NO_CHECK = SiteCheck(
    kind="bound_values",
    subject="the strategy on the site",
    status="unchecked",
    evidence="no step of the strategy binds a value to compare",
    why_unchecked="no_check",
)


def _digest(*checks: SiteCheck) -> VerificationDigest:
    return VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose="The site did not answer the strategy read.",
        reason="The site did not answer, so the strategy is not checked",
        success=False,
        review=VerificationReview(checks=list(checks)),
    )


_UNANSWERED = _digest(*unanswered_checks("the site did not answer the strategy read"))


def test_a_digest_is_not_checked_only_when_the_site_did_not_answer() -> None:
    objected = _UNANSWERED.model_copy(update={"disposition": PhaseDisposition.HANDOFF})

    assert [d.not_checked for d in (_UNANSWERED, _digest(_NO_CHECK), objected)] == [
        True,
        False,
        False,
    ]
    assert (_UNANSWERED.passed, VerificationSection(digest=_UNANSWERED).successful) == (
        False,
        False,
    )


def test_every_reader_says_the_site_did_not_answer() -> None:
    result = ToolReturnPart(
        tool_name="verify_strategy",
        content=VerificationDelta(digest=_UNANSWERED).model_dump(mode="json"),
        tool_call_id="c1",
    )

    assert [
        _summarize_sub_agent_result("verify_strategy", result),
        turn_budget._verdict(_UNANSWERED),
    ] == [
        "Not checked: the site did not answer",
        "Not verified: the site did not answer the check.",
    ]
    lines = render_verification_full(VerificationSection(digest=_UNANSWERED))
    assert "- verdict: not checked, the site did not answer" in lines.splitlines()
