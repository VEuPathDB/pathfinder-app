"""What a stored audit run is doing now, the action its page may take next, and the units it left unread or unreached."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field

from pathfinder.domain.audit.findings import EvidenceKind, EvidenceStatus, FindingTally
from pathfinder.domain.audit.scope import GenomeStatus
from pathfinder.domain.audit.stages import RunStatus
from pathfinder.domain.audit.verdicts import ReviewProgress

RunPhase = Literal["not_started", "queued", "running", "halted", "finished"]
RunAction = Literal["resume", "retry"]
_LEFT = frozenset({"unreached", "unread"})
_REVIEWING = frozenset({"waiting", "reviewing"})


class EvidenceTally(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: EvidenceKind
    status: EvidenceStatus
    count: int = Field(ge=0)


class LeftUnits(CamelModel):
    model_config = ConfigDict(frozen=True)

    genomes: int = Field(ge=0)
    findings: int = Field(ge=0)
    evidence: int = Field(ge=0)

    @computed
    def total(self) -> int:
        return self.genomes + self.findings + self.evidence


def left_units(
    genomes: Iterable[GenomeStatus],
    findings: Iterable[FindingTally],
    evidence: Iterable[EvidenceTally],
) -> LeftUnits:
    return LeftUnits(
        genomes=sum(status in _LEFT for status in genomes),
        findings=sum(row.count for row in findings if row.status in _LEFT),
        evidence=sum(row.count for row in evidence if row.status in _LEFT),
    )


def run_phase(
    status: RunStatus, *, halted: bool, deadline_at: datetime | None
) -> RunPhase:
    match (status, halted, deadline_at):
        case ("finished", _, _):
            return "finished"
        case (_, True, _):
            return "halted"
        case ("running", _, _):
            return "running"
        case ("planned", _, None):
            return "not_started"
        case _:
            return "queued"


def reviews_running(phase: RunPhase, review: ReviewProgress | None) -> bool:
    return phase == "finished" and review is not None and review.status in _REVIEWING


def run_action(
    phase: RunPhase, left: LeftUnits, *, reviews_running: bool
) -> RunAction | None:
    match phase:
        case "halted":
            return "resume"
        case "finished" if left.total and not reviews_running:
            return "retry"
        case _:
            return None
