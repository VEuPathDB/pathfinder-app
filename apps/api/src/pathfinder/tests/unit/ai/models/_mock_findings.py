"""A check that found a gap and measured two caveats, as the verify tool
answers it."""

from __future__ import annotations

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.domain.caveats import (
    Caveat,
    ControlsCaveat,
    Gap,
    RequirementGap,
    SampleCaveat,
)
from pathfinder.tests._support.column_fits import tm_fit

CONTROLS = ControlsCaveat(positives_returned=7, positives_total=10)
SAMPLE = SampleCaveat(fit=tm_fit(12, 40))
UNMET = RequirementGap(text="annotated as essential", status="unmet")
CAVEATS: tuple[Caveat, ...] = (CONTROLS, SAMPLE)
GAPS: tuple[Gap, ...] = (UNMET,)


def checked(
    *, caveats: tuple[Caveat, ...] = CAVEATS, gaps: tuple[Gap, ...] = GAPS
) -> VerificationDelta:
    """The verify tool's answer: the digest held to failure when a gap exists."""
    return VerificationDelta(
        digest=VerificationDigest(
            disposition=PhaseDisposition.AWAITING_USER
            if gaps
            else PhaseDisposition.DONE,
            prose="The check read the strategy.",
            reason="mock verification",
            success=not gaps,
            caveats=list(caveats),
            gaps=list(gaps),
        )
    )
