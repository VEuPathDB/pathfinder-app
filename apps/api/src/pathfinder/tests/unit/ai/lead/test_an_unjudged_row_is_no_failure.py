"""A row a step answers and no sampled record judged is shown as a gap, and
never holds the check short of success."""

from __future__ import annotations

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import _findings
from pathfinder.domain.caveats import RequirementGap
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_NO_BUILD = "The build pushed 0 steps, failed 0, skipped 0 and left 0 empty"
_SIGNAL = requirement(ConstraintKind.OTHER, "localisation", "signal peptide")


def _deps() -> LeadDeps:
    state = pipeline_state("toxodb", domain=StrategyDomainState(requirements=[_SIGNAL]))
    return lead_deps(state, intent=None)


def _row(**fields: object) -> RequirementCheck:
    return RequirementCheck.model_validate(
        {
            "text": "signal peptide",
            "turn": 1,
            "answeredBy": ["c_signal"],
            "how": "search",
            "status": "met",
        }
        | fields
    )


def test_an_unjudged_row_is_a_gap_and_no_failure() -> None:
    review = VerificationReview(requirements=[_row(no_record_judged_it=True)])

    findings = _findings(_deps(), review, [])

    assert (findings.gaps, findings.sentence()) == (
        [RequirementGap(text="signal peptide", status="unjudged")],
        _NO_BUILD,
    )


def test_an_unmet_row_is_a_failure() -> None:
    review = VerificationReview(requirements=[_row(status="unmet", answeredBy=[])])

    assert _findings(_deps(), review, []).sentence() == (
        f"{_NO_BUILD}; 'signal peptide': nothing in the strategy answers it"
    )
