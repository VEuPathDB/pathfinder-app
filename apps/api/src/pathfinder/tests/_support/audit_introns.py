"""Synthetic intron-check answers, one for each verdict the library gives."""

from __future__ import annotations

from veupathdb_mcp.audit import (
    GeneId,
    IntronAudit,
    IntronDepth,
    IntronJudgement,
    IntronSupport,
    IntronVerdict,
    UnreadIntron,
    UnreadOutcome,
)

INTRON_GENE = "EXA_0002"
_READ = IntronSupport(start=1101, end=1300, reads=120, tracks=2)
_UNREAD_SPAN = (1501, 1700)


def _replacement(outcome: UnreadOutcome) -> list[IntronSupport]:
    match outcome:
        case "SHIFTED" | "REPLACED":
            return [IntronSupport(start=1490, end=1690, reads=80, tracks=1)]
        case "MISSING_EXON":
            return [
                IntronSupport(start=1501, end=1580, reads=70, tracks=1),
                IntronSupport(start=1620, end=1700, reads=65, tracks=1),
            ]
        case _:
            return []


def _unread(outcome: UnreadOutcome) -> UnreadIntron:
    start, end = _UNREAD_SPAN
    return UnreadIntron(
        start=start,
        end=end,
        in_cds=True,
        outcome=outcome,
        replacement=_replacement(outcome),
        motif="AT..AC" if outcome == "NONCANONICAL" else None,
        depth=IntronDepth(
            intron_median_depth=40.0,
            exon_median_depth=60.0,
            covered_share=0.95,
            track="exampleCoverage",
        )
        if outcome == "RETAINED"
        else None,
    )


_OUTCOMES: dict[IntronVerdict, UnreadOutcome] = {
    "UNSUPPORTED_SHIFTED": "SHIFTED",
    "UNSUPPORTED_MISSING_EXON": "MISSING_EXON",
    "UNSUPPORTED_REPLACED": "REPLACED",
    "UNSUPPORTED_NONCANONICAL": "NONCANONICAL",
    "UNSUPPORTED_RETAINED": "RETAINED",
    "UNSUPPORTED_UNEXPLAINED": "UNEXPLAINED",
}
_CORRECTABLE = frozenset(_OUTCOMES) - {"UNSUPPORTED_UNEXPLAINED"}


def _judged(verdict: IntronVerdict) -> IntronJudgement:
    match verdict:
        case "NOT_CHECKED":
            return IntronJudgement.not_checked("no junction track for the genome")
        case "NOT_EXPRESSED":
            return IntronJudgement(
                verdict=verdict, introns=[_READ], unread=None, best_junction_reads=12
            )
        case "SUPPORTED":
            return IntronJudgement(
                verdict=verdict, introns=[_READ], unread=[], best_junction_reads=120
            )
        case _:
            return IntronJudgement(
                verdict=verdict,
                introns=[_READ],
                unread=[_unread(_OUTCOMES[verdict])],
                best_junction_reads=120,
            )


def intron_audit(verdict: IntronVerdict) -> IntronAudit:
    return IntronAudit(
        **_judged(verdict).model_dump(),
        gene_ids=[GeneId(given=INTRON_GENE, resolved=INTRON_GENE)],
        gene=INTRON_GENE,
        transcript=f"{INTRON_GENE}-t1",
        other_transcripts=0,
        tracks_refused=None,
        evidence_unread=[],
        corrected_cds=None,
        corrected_protein=None,
        frame_kept=None,
        code=None,
        code_inferred=False,
        orthologs=None,
        correction_reason="the correction is not read"
        if verdict in _CORRECTABLE
        else None,
    )
