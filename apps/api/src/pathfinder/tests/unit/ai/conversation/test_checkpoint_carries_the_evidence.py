"""The control tests and the card of a checked turn survive a checkpoint."""

from __future__ import annotations

from datetime import UTC, datetime

from assistant_core.conversation.serde import build_checkpoint_serde

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.graph.turn_records import ControlTestRun
from pathfinder.assistants.pathfinder_spec import PATHFINDER_CHECKPOINT_TYPES
from pathfinder.domain.evidence import (
    ControlSetEvidence,
    ControlTestEvidence,
    EvidenceCard,
    EvidenceVerdict,
)


def test_a_checked_turns_evidence_survives_strict_roundtrip() -> None:
    """They ride the turn record inside the domain, which is allowlisted."""
    domain = StrategyDomainState()
    tested = ControlTestEvidence(
        tested_label="Kinases",
        wdk_step_id=440299573,
        positive=ControlSetEvidence(
            returned=["PF3D7_0102600"], not_returned=["PF3D7_1133400"]
        ),
    )
    domain.turn_markers.record_control_tests(
        [ControlTestRun(tool_call_id="call_controls", evidence=tested)]
    )
    domain.last_evidence_card = EvidenceCard(
        check_id="call_verify",
        revision="rev-1",
        site_id="plasmodb",
        checked_at=datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
        site_read="not_answered",
        steps=[],
        controls=[tested],
        citations=[],
        verdict=EvidenceVerdict(supported=True),
    )
    serde = build_checkpoint_serde(PATHFINDER_CHECKPOINT_TYPES)

    restored = serde.loads_typed(serde.dumps_typed(domain))

    assert isinstance(restored, StrategyDomainState)
    assert restored.turn_markers == domain.turn_markers
    assert restored.last_evidence_card == domain.last_evidence_card
