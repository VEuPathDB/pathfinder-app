from __future__ import annotations

from pathlib import Path
from uuid import UUID

from pydantic import BaseModel

from pathfinder.ai.audit.facts import audit_finding_fact
from pathfinder.ai.lead.contract_messages import unrendered_prose_message
from pathfinder.ai.lead.withheld_reply import withholds
from pathfinder.domain.reply_references import prose_faults
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.services.audit.finding_views import FindingDetail

_RECORDED = Path(__file__).parents[2] / "fixtures/turns/fungidb_audit_finding_read.json"


class _Read(BaseModel):
    run_id: UUID
    answer: FindingDetail
    drafts: list[str]


def _read() -> tuple[TurnFacts, list[str], str]:
    read = _Read.model_validate_json(_RECORDED.read_text())
    fact = audit_finding_fact(read.run_id, read.answer)
    return TurnFacts(audit_statistics=[fact]), read.drafts, fact.id


def _named(prose: str, facts: TurnFacts) -> list[tuple[str, str, tuple[str, ...]]]:
    return [
        (f.kind, f.token, f.references)
        for f in prose_faults(prose, facts)
        if f.kind == "misnamed_reference"
    ]


def test_a_path_that_ends_a_held_row_is_told_that_row() -> None:
    facts, drafts, fact = _read()

    assert _named(drafts[0], facts) == [
        (
            "misnamed_reference",
            f"[cite:{fact}.verdict.cause]",
            (f"[cite:{fact}.review.verdict.cause]",),
        ),
        (
            "misnamed_reference",
            f"[stat:{fact}.verdict.certainty]",
            (f"[stat:{fact}.review.verdict.certainty]",),
        ),
    ]


def test_a_path_whose_last_name_rows_hold_is_told_each_of_them() -> None:
    facts, drafts, fact = _read()

    assert _named(drafts[1], facts) == [
        (
            "misnamed_reference",
            f"[cite:{fact}.review.verdict.impactReason]",
            (
                f"[cite:{fact}.finding.reviewLine.impactReason]",
                f"[cite:{fact}.review.impactReason]",
            ),
        )
    ]
    message = unrendered_prose_message(prose_faults(drafts[1], facts))
    assert f"[cite:{fact}.review.impactReason]" in message
    assert "names no row of its fact" in message


def test_a_reply_that_keeps_a_misnamed_row_is_withheld() -> None:
    facts, drafts, _ = _read()
    misnamed = [
        f for f in prose_faults(drafts[1], facts) if f.kind == "misnamed_reference"
    ]

    assert (len(misnamed), withholds(misnamed)) == (1, True)


def test_a_stat_is_never_told_a_sentence_row() -> None:
    facts, _, fact = _read()
    prose = f"The review reads [stat:{fact}.verdict.cause]."

    assert [(f.kind, f.references) for f in prose_faults(prose, facts)] == [
        ("unheld_reference", ())
    ]
