"""The verdict an extract reads carries the check's requirement rows, and the
card's review, redacted."""

from __future__ import annotations

from datetime import UTC, datetime

from assistant_core.platform.types import JSONObject

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.graph.stream_events import evidence_card_event, ledger_update_event
from pathfinder.ai.lead.ledger_sections import VerificationSection
from pathfinder.domain.evidence import (
    Citation,
    EvidenceCard,
    EvidenceVerdict,
    RequirementCheck,
    SampledGene,
    VerificationReview,
)
from pathfinder.services.eval_data.chunk_reader import LoggedChunk, read_verification
from pathfinder.tests._support.ledger import ledger_with

_REVIEW = VerificationReview(
    requirements=[
        RequirementCheck(
            text="the genes ada@example.org asked for",
            turn=1,
            answered_by=["s1"],
            how="search",
            status="met",
            note="GenesWithSignalPeptide",
        )
    ],
    sampled_genes=[
        SampledGene(
            gene_id="PF3D7_0102200",
            product="ring-infected erythrocyte surface antigen",
            organism="Plasmodium falciparum 3D7",
            fits="yes",
            why="as ada@example.org expects",
        )
    ],
    sources=[
        Citation(
            kind="web",
            label="A page",
            url="https://user:secret@example.org/page",
            why="it defines exported",
        )
    ],
)


def _chunks() -> list[LoggedChunk]:
    digest = VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose="prose",
        reason="checked",
        success=True,
        review=_REVIEW,
    )
    ledger = ledger_update_event(
        ledger=ledger_with(VerificationSection(digest=digest))
    ).model_dump(by_alias=True, mode="json", exclude_none=True)
    card: JSONObject = evidence_card_event(
        EvidenceCard(
            check_id="call_verify",
            revision="rev-1",
            site_id="plasmodb",
            checked_at=datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
            site_read="not_read",
            steps=[],
            controls=[],
            citations=[],
            verdict=EvidenceVerdict(supported=True),
            review=_REVIEW,
        )
    ).model_dump(by_alias=True, mode="json", exclude_none=True)
    return [LoggedChunk.model_validate({"chunk": c}) for c in (ledger, card)]


def test_the_verdict_carries_its_requirement_rows_redacted() -> None:
    verdict = read_verification(_chunks())

    assert verdict is not None
    assert [row.text for row in verdict.requirements] == [
        "the genes [redacted-email] asked for"
    ]


def test_the_cards_review_is_redacted() -> None:
    verdict = read_verification(_chunks())

    assert verdict is not None
    assert verdict.evidence is not None
    review = verdict.evidence.review
    assert (
        review.requirements[0].text,
        review.sampled_genes[0].why,
        review.sources[0].url,
    ) == (
        "the genes [redacted-email] asked for",
        "as [redacted-email] expects",
        "https://[redacted-credential]@example.org/page",
    )
