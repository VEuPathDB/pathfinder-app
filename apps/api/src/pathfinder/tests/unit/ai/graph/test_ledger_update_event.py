"""The ledger and evidence chunks carry every key their schemas require."""

from datetime import UTC, datetime

from pathfinder.ai.graph.stream_events import (
    evidence_card_event,
    ledger_update_event,
)
from pathfinder.ai.lead.ledger import InvestigationLedger
from pathfinder.ai.lead.ledger_sections import (
    BuildSection,
    FrameSection,
    VerificationSection,
)
from pathfinder.domain.evidence import EvidenceCard, EvidenceVerdict


def _required_keys(model: type[InvestigationLedger]) -> frozenset[str]:
    schema = model.model_json_schema(mode="serialization")
    return frozenset(schema["required"])


def _empty_ledger() -> InvestigationLedger:
    return InvestigationLedger(
        user_intent=None,
        frame=FrameSection(),
        build=BuildSection(),
        verification=VerificationSection(),
    )


def test_ledger_chunk_carries_every_required_top_level_key() -> None:
    chunk = ledger_update_event(ledger=_empty_ledger())
    assert isinstance(chunk.data, dict)
    assert _required_keys(InvestigationLedger) <= frozenset(chunk.data)


def test_ledger_chunk_carries_the_nullable_section_fields() -> None:
    chunk = ledger_update_event(ledger=_empty_ledger())
    assert chunk.data == {
        "userIntent": None,
        "frame": {
            "spec": None,
            "present": False,
            "diff": None,
            "criteriaCount": 0,
            "boundCount": 0,
            "openSlotCount": 0,
            "droppedCount": 0,
            "readyToBuild": False,
            "needsUser": False,
            "contrasts": [],
            "structureRender": None,
        },
        "build": {
            "outcome": None,
            "staleBuild": None,
            "pushedCount": 0,
            "failedCount": 0,
            "skippedCount": 0,
            "zeroResultSteps": [],
            "needsRecovery": False,
            "recoveryKind": "none",
            "succeeded": False,
            "nodeResults": [],
            "wdkStrategyId": None,
            "wdkUrl": None,
        },
        "verification": {"digest": None, "complete": False, "successful": False},
        "constraints": {"grounded": [], "unmetCount": 0, "blocking": False},
        "declinedProposal": None,
    }


def test_ledger_chunk_sections_carry_every_required_key() -> None:
    chunk = ledger_update_event(ledger=_empty_ledger())
    assert isinstance(chunk.data, dict)
    for field, section in (
        ("frame", FrameSection),
        ("build", BuildSection),
        ("verification", VerificationSection),
    ):
        payload = chunk.data[field]
        assert isinstance(payload, dict)
        required = frozenset(
            section.model_json_schema(mode="serialization")["required"]
        )
        assert required <= frozenset(payload), field


def test_evidence_card_chunk_matches_its_payload_model() -> None:
    card = EvidenceCard(
        check_id="call_verify",
        revision="rev-1",
        site_id="plasmodb",
        checked_at=datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
        site_read="not_answered",
        steps=[],
        controls=[],
        citations=[],
        verdict=EvidenceVerdict(supported=True),
    )

    chunk = evidence_card_event(card)

    assert chunk.type == "data-evidence-card"
    assert isinstance(chunk.data, dict)
    required = frozenset(
        EvidenceCard.model_json_schema(mode="serialization")["required"]
    )
    assert required <= frozenset(chunk.data)
    assert chunk.data["checkId"] == "call_verify"
