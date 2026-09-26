"""A check that found a gap and measured two caveats, as the verify tool
answers it, and the turn record that holds the same findings."""

from __future__ import annotations

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.turn_record import TurnRecord
from pathfinder.ai.models.mock.reply_faults import UNMET_REQUIREMENT
from pathfinder.domain.caveats import (
    Caveat,
    ControlsCaveat,
    Gap,
    RequirementGap,
    SampleCaveat,
)
from pathfinder.domain.evidence import (
    ControlSetEvidence,
    ControlTestEvidence,
    SampledGene,
)

CONTROLS = ControlsCaveat(positives_returned=7, positives_total=10)
SAMPLE = SampleCaveat(unclear=1, misfit=0, total=2)
UNMET = RequirementGap(text=UNMET_REQUIREMENT, status="unmet")
CAVEATS: tuple[Caveat, ...] = (CONTROLS, SAMPLE)
GAPS: tuple[Gap, ...] = (UNMET,)
TESTED = ControlTestEvidence(
    tested_label="Kinases",
    wdk_step_id=440299573,
    positive=ControlSetEvidence(
        returned=[f"PF3D7_{n:07d}" for n in range(1133400, 1133407)],
        not_returned=["PF3D7_0102600", "PF3D7_0213400", "PF3D7_0303900"],
    ),
)
SAMPLED = (
    SampledGene(gene_id="PF3D7_1133400", fits="yes", why="the record names it"),
    SampledGene(gene_id="PF3D7_1133401", fits="unclear", why="the record is silent"),
)


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


def holding(
    record: TurnRecord,
    *,
    caveats: tuple[Caveat, ...] = CAVEATS,
    gaps: tuple[Gap, ...] = GAPS,
) -> TurnRecord:
    """The record with the check's findings and the results that back them."""
    return record.model_copy(
        update={
            "caveats": caveats,
            "gaps": gaps,
            "control_results": (TESTED,),
            "sampled_genes": SAMPLED,
        }
    )
