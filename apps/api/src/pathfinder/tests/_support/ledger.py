"""Test-only construction of a whole ledger around one section."""

from __future__ import annotations

from pathfinder.ai.lead.ledger import InvestigationLedger
from pathfinder.ai.lead.ledger_sections import (
    BuildSection,
    FrameSection,
    VerificationSection,
)


def ledger_with(verification: VerificationSection) -> InvestigationLedger:
    """A ledger whose only filled section is the verification."""
    return InvestigationLedger(
        user_intent=None,
        frame=FrameSection(),
        build=BuildSection(),
        verification=verification,
    )
