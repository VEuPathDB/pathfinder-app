"""A stored run's phase, the action the page may take next, and the units it left open."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pathfinder.domain.audit.findings import FindingTally
from pathfinder.domain.audit.run_state import (
    EvidenceTally,
    LeftUnits,
    RunPhase,
    left_units,
    reviews_running,
    run_action,
    run_phase,
)
from pathfinder.domain.audit.scope import GenomeStatus
from pathfinder.domain.audit.stages import (
    SIGN_IN_NEEDED,
    RunHalt,
    RunStages,
    RunStatus,
)
from pathfinder.domain.audit.verdicts import ReviewProgress, ReviewStatus

NF54 = "Plasmodium falciparum NF54"
DEADLINE = datetime(2026, 10, 21, 18, 0, tzinfo=UTC)
FAILED = "the audit job failed: KeyError: 'PF3D7_1032400'"


def _finding(status: str, count: int) -> FindingTally:
    return FindingTally.model_validate(
        {
            "genome": NF54,
            "check": "gene_length",
            "status": status,
            "error_type": None,
            "judged": True,
            "model_genome": NF54,
            "count": count,
        }
    )


@pytest.mark.parametrize(
    ("status", "halted", "deadline", "phase"),
    [
        ("planned", False, None, "not_started"),
        ("planned", False, DEADLINE, "queued"),
        ("running", False, DEADLINE, "running"),
        ("running", True, DEADLINE, "halted"),
        ("planned", True, None, "halted"),
        ("finished", False, DEADLINE, "finished"),
    ],
)
def test_a_run_reads_as_one_phase(
    status: RunStatus, halted: bool, deadline: datetime | None, phase: RunPhase
) -> None:
    assert run_phase(status, halted=halted, deadline_at=deadline) == phase


def test_the_units_left_count_only_unreached_and_unread() -> None:
    genomes: list[GenomeStatus] = ["collected", "unreached", "unread", "failed"]
    left = left_units(
        genomes,
        [_finding("unread", 2), _finding("unreached", 1), _finding("failed", 4)],
        [
            EvidenceTally(kind="gene_evidence", status="unread", count=3),
            EvidenceTally(kind="relatives", status="stored", count=5),
        ],
    )
    assert left == LeftUnits(genomes=2, findings=3, evidence=3)
    assert left.total == 8


def test_a_halted_run_offers_resume_and_a_finished_one_with_units_left_offers_retry() -> (
    None
):
    none_left = LeftUnits(genomes=0, findings=0, evidence=0)
    one_left = LeftUnits(genomes=0, findings=0, evidence=1)
    assert [
        run_action("halted", none_left, reviews_running=False),
        run_action("finished", one_left, reviews_running=False),
        run_action("finished", none_left, reviews_running=False),
        run_action("running", one_left, reviews_running=False),
        run_action("queued", none_left, reviews_running=False),
        run_action("not_started", none_left, reviews_running=False),
        run_action("finished", one_left, reviews_running=True),
    ] == ["resume", "retry", None, None, None, None, None]


def test_a_finished_run_whose_reviews_run_offers_nothing() -> None:
    statuses: list[ReviewStatus] = ["waiting", "reviewing", "synthesized", "stopped"]
    assert [
        reviews_running("finished", ReviewProgress(status=status))
        for status in statuses
    ] == [True, True, False, False]
    assert reviews_running("finished", None) is False
    assert reviews_running("running", ReviewProgress(status="waiting")) is False


def test_a_halt_names_its_kind_and_keeps_its_detail() -> None:
    assert RunStages().halt_reason is None
    assert RunStages().halt(SIGN_IN_NEEDED).halt_reason == RunHalt(
        kind="sign_in", detail="sign-in needed"
    )
    assert RunStages().halt(FAILED).halt_reason == RunHalt(
        kind="task_failed", detail=FAILED
    )
