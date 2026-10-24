from __future__ import annotations

from veupathdb_mcp.audit import (
    RETAINED_MIN_COVERED,
    RETAINED_MIN_SHARE,
    IntronAudit,
    IntronDepth,
    IntronSupport,
    OrthologSupport,
    UnreadIntron,
    UnreadOutcome,
)

from pathfinder.domain.audit.facts import NONE, NOT_READ, Fact, counted, known, listed

_OUTCOMES: dict[UnreadOutcome, str] = {
    "SHIFTED": "a junction a few bases away",
    "MISSING_EXON": "junctions that join an exon the model lacks",
    "REPLACED": "a junction that replaces it",
    "NONCANONICAL": "its splice-site bases are not canonical",
    "RETAINED": "reads cover it and none splices it",
    "UNEXPLAINED": "nothing explains it",
}
_ACROSS_GAP = "it spans an assembly gap, so its splice-site bases were not read"


def _percent(share: float) -> str:
    return f"{round(100 * share)}%"


def _junction(junction: IntronSupport) -> str:
    return (
        f"{junction.start:,} to {junction.end:,} "
        f"({counted(junction.reads, 'read', 'reads')}; tracks: {junction.tracks})"
    )


def _depth(depth: IntronDepth) -> str:
    return (
        f"median {depth.intron_median_depth:g} against an exon median of "
        f"{depth.exon_median_depth:g} ({_percent(depth.depth_share)}; RETAINED needs "
        f"{_percent(RETAINED_MIN_SHARE)} or more), {_percent(depth.covered_share)} of its "
        f"bases covered (RETAINED needs {_percent(RETAINED_MIN_COVERED)} or more), "
        f"track {depth.track}"
    )


def _shown(intron: UnreadIntron, unread: list[str]) -> str:
    gap = f"the intron {intron.start}-{intron.end} spans an assembly gap"
    across = intron.outcome == "UNEXPLAINED" and gap in unread
    return _ACROSS_GAP if across else _OUTCOMES[intron.outcome]


def _unread_intron(intron: UnreadIntron, unread: list[str]) -> tuple[Fact, ...]:
    motif = (
        ()
        if intron.motif is None
        else (Fact(label="Splice-site bases", value=intron.motif),)
    )
    depth = (
        ()
        if intron.depth is None
        else (Fact(label="Read depth", value=_depth(intron.depth)),)
    )
    return (
        Fact(
            label="Intron with no read",
            value=f"bases {intron.start:,} to {intron.end:,}",
        ),
        Fact(label="What the RNA-seq shows there", value=_shown(intron, unread)),
        *motif,
        Fact(
            label="RNA-seq junctions that replace it",
            value=listed([_junction(j) for j in intron.replacement]),
        ),
        *depth,
    )


def _with_reads(result: IntronAudit) -> str:
    if result.introns is None:
        return NOT_READ
    read = sum(intron.reads > 0 for intron in result.introns)
    return f"{read:,} of {len(result.introns):,}"


def _corrected(result: IntronAudit) -> str:
    protein = result.corrected_protein
    if protein is None:
        return NOT_READ
    frame = "frame kept" if result.frame_kept else "frame not kept"
    return f"{counted(len(protein), 'residue', 'residues')}, {frame}"


def _orthologs(orthologs: OrthologSupport | None) -> str:
    if orthologs is None:
        return NOT_READ
    match (orthologs.for_corrected, orthologs.for_annotated, orthologs.read):
        case (int(corrected), int(annotated), int(read)):
            return (
                f"{corrected:,} for the corrected model, {annotated:,} for the "
                f"annotated one, of {read:,} read"
            )
        case _:
            return known(orthologs.reason)


def intron_facts(result: IntronAudit) -> tuple[Fact, ...]:
    unread = result.evidence_unread
    reason = result.correction_reason
    why = () if reason is None else (Fact(label="Why no correction", value=reason),)
    return (
        Fact(label="Transcript judged", value=known(result.transcript)),
        Fact(label="Annotated introns with reads", value=_with_reads(result)),
        *(
            fact
            for intron in result.unread or []
            for fact in _unread_intron(intron, unread)
        ),
        Fact(label="Evidence not read", value="; ".join(unread) or NONE),
        Fact(label="Corrected protein", value=_corrected(result)),
        Fact(label="Orthologs that match", value=_orthologs(result.orthologs)),
        *why,
    )
