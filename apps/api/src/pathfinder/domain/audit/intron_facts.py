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

from pathfinder.domain.audit.facts import (
    NOT_READ,
    Fact,
    counted,
    known,
    listed,
    unread_facts,
)
from pathfinder.domain.audit.words import percent

_OUTCOMES: dict[UnreadOutcome, str] = {
    "SHIFTED": "an RNA-seq junction a few bases away",
    "MISSING_EXON": "RNA-seq junctions that join an exon the model lacks",
    "REPLACED": "an RNA-seq junction that replaces it",
    "NONCANONICAL": "the genome's splice-site bases are not canonical",
    "RETAINED": "RNA-seq reads cover it and none splices it",
    "UNEXPLAINED": "no evidence explains it",
}
_ACROSS_GAP = "it spans an assembly gap, so its splice-site bases were not read"


def _junction(junction: IntronSupport) -> str:
    return (
        f"{junction.start:,} to {junction.end:,} "
        f"({counted(junction.reads, 'read', 'reads')}; tracks: {junction.tracks})"
    )


def _depth(depth: IntronDepth) -> str:
    return (
        f"median {depth.intron_median_depth:g} against an exon median of "
        f"{depth.exon_median_depth:g} ({percent(depth.depth_share)}; RETAINED needs "
        f"{percent(RETAINED_MIN_SHARE)} or more), {percent(depth.covered_share)} of its "
        f"bases covered (RETAINED needs {percent(RETAINED_MIN_COVERED)} or more), "
        f"track {depth.track}"
    )


def _shown(intron: UnreadIntron) -> str:
    shown = _OUTCOMES[intron.outcome]
    return f"{shown}; {_ACROSS_GAP}" if intron.spans_assembly_gap else shown


def _unread_intron(intron: UnreadIntron) -> tuple[Fact, ...]:
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
        Fact(label="What the evidence shows there", value=_shown(intron)),
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
    if orthologs.reason is not None:
        return orthologs.reason
    return (
        f"{orthologs.for_corrected:,} for the corrected model, "
        f"{orthologs.for_annotated:,} for the annotated one, of {orthologs.read:,} read"
    )


def intron_facts(result: IntronAudit) -> tuple[Fact, ...]:
    unread = result.evidence_unread
    reason = result.correction_reason
    why = () if reason is None else (Fact(label="Why no correction", value=reason),)
    return (
        Fact(label="Transcript judged", value=known(result.transcript)),
        Fact(label="Annotated introns with reads", value=_with_reads(result)),
        *(fact for intron in result.unread or [] for fact in _unread_intron(intron)),
        *unread_facts(unread),
        Fact(label="Corrected protein", value=_corrected(result)),
        Fact(label="Orthologs that match", value=_orthologs(result.orthologs)),
        *why,
    )
