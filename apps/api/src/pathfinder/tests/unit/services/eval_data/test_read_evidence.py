"""The extract records the last evidence card of the thread beside its verdict."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from assistant_core.platform.types import JSONObject
from pydantic import ValidationError

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.graph.stream_events import evidence_card_event, ledger_update_event
from pathfinder.ai.lead.ledger_sections import VerificationSection
from pathfinder.domain.evidence import (
    CheckedStepCount,
    ControlSetEvidence,
    ControlTestEvidence,
    EvidenceCard,
    EvidenceVerdict,
)
from pathfinder.evals.extract import (
    EvalExtract,
    ExtractedTurn,
    ExtractedVerification,
)
from pathfinder.services.eval_data.chunk_reader import LoggedChunk, read_verification
from pathfinder.tests._support.ledger import ledger_with

_URL = "https://plasmodb.org/plasmo/app/workspace/strategies/300125410/440299573"


def _card(check_id: str, *, url: str = _URL, site_count: int = 212) -> EvidenceCard:
    return EvidenceCard(
        check_id=check_id,
        revision="rev-1",
        site_id="plasmodb",
        checked_at=datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
        wdk_strategy_id=300125410,
        strategy_url=url,
        site_read="read",
        steps=[
            CheckedStepCount(
                step_id="s1",
                wdk_step_id=440299573,
                title="Kinases",
                recorded_count=212,
                site_count=site_count,
            )
        ],
        controls=[
            ControlTestEvidence(
                tested_label="Kinases",
                wdk_step_id=440299573,
                positive=ControlSetEvidence(
                    returned=["PF3D7_1133400"], not_returned=["PF3D7_0102600"]
                ),
            )
        ],
        citations=[],
        verdict=EvidenceVerdict(supported=True),
    )


def _card_chunk(card: EvidenceCard) -> JSONObject:
    return evidence_card_event(card).model_dump(by_alias=True, mode="json")


def _ledger_chunk() -> JSONObject:
    digest = VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose="prose",
        reason="checked",
        success=True,
    )
    chunk = ledger_update_event(ledger=ledger_with(VerificationSection(digest=digest)))
    return chunk.model_dump(by_alias=True, mode="json", exclude_none=True)


def _log(*chunks: JSONObject) -> list[LoggedChunk]:
    return [LoggedChunk.model_validate({"chunk": chunk}) for chunk in chunks]


def test_the_last_card_rides_the_verdict() -> None:
    first = _card("call_verify_1", site_count=212)
    last = _card("call_verify_2", site_count=230)

    verdict = read_verification(
        _log(_card_chunk(first), _ledger_chunk(), _card_chunk(last), _ledger_chunk())
    )

    assert verdict is not None
    assert verdict.evidence == last


def test_a_thread_with_no_card_records_none() -> None:
    verdict = read_verification(_log(_ledger_chunk()))

    assert verdict is not None
    assert (verdict.success, verdict.evidence) == (True, None)


def test_the_card_is_read_redacted() -> None:
    leaked = "https://ahmed:secret@plasmodb.org/plasmo/app/workspace/strategies/3/4"

    verdict = read_verification(
        _log(_card_chunk(_card("call_verify", url=leaked)), _ledger_chunk())
    )

    assert verdict is not None
    assert verdict.evidence is not None
    assert verdict.evidence.strategy_url == (
        "https://[redacted-credential]@plasmodb.org/plasmo/app/workspace/strategies/3/4"
    )


def test_an_extract_whose_card_carries_a_credential_cannot_be_built() -> None:
    leaked = "https://ahmed:secret@plasmodb.org/plasmo/app/workspace/strategies/3/4"

    with pytest.raises(ValidationError, match="URL credential"):
        EvalExtract(
            site_id="plasmodb",
            assistant_id="pathfinder",
            turns=[ExtractedTurn(request="find kinases")],
            verification=ExtractedVerification(
                success=True, evidence=_card("call_verify", url=leaked)
            ),
        )
