from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from veupathdb_mcp.audit import (
    GeneFusionAudit,
    GeneLengthAudit,
    LengthCheck,
    LengthScreen,
    MissingGeneAudit,
    NoRelatives,
    NotRead,
    OrganelleGeneAudit,
    PseudogeneCallAudit,
    RelativeTier,
    SelenoproteinEndAudit,
    StrainModelAudit,
    WindowState,
)

from pathfinder.domain.audit.confirmations import (
    Confirmation,
    FusionConfirmation,
    IntronConfirmation,
    LengthConfirmation,
    MissingGeneConfirmation,
    OrganelleConfirmation,
    PseudogeneConfirmation,
    SelenoproteinConfirmation,
    StrainConfirmation,
)
from pathfinder.domain.audit.facts import (
    NONE,
    NOT_READ,
    YES_NO,
    EvidenceFacts,
    Fact,
    code_text,
    gene_evidence_facts,
    known,
    listed,
    relatives_facts,
    residues,
    runs_text,
    unread_facts,
)
from pathfinder.domain.audit.findings import (
    ConfirmationEvidence,
    EvidencePayload,
    GeneEvidencePayload,
    RelativesEvidence,
)
from pathfinder.domain.audit.intron_facts import intron_facts
from pathfinder.domain.audit.words import LENGTH_SENTENCES

_WINDOWS: dict[WindowState | Literal["part1", "part2"], str] = {
    "model": "in the model",
    "genome_same_strand": "encoded on the same strand outside the model",
    "genome_other_strand": "encoded on the other strand",
    "absent": "not encoded",
    "weak": "matched weakly",
    "part1": "in the first model",
    "part2": "in the second model",
}
_TIERS: dict[RelativeTier, str] = {
    "SAME_GENUS": "The same genus",
    "OTHER_GENERA": "Other genera",
}
_NO_RELATIVES: dict[NoRelatives, str] = {
    "RESIDUAL_GROUP": "the ortholog group is a residual group",
    "PARALOGS": "the related genomes do not hold one copy each",
    "FEWER_THAN_TWO": "fewer than two independent related genomes hold the gene",
}
_NOT_READ: dict[NotRead, str] = {
    "NO_LOST_RUN": "The strain protein lacks no run of the reference protein",
    "UNQUALIFIED": "The ortholog group is a residual group",
    "PARALOG_IN_WINDOW": "A paralog lies in the window the check reads",
}


def _positions(at: Sequence[int]) -> str:
    if not at:
        return NONE
    word = "residue" if len(at) == 1 else "residues"
    return f"at {word} {listed([f'{n:,}' for n in at])}"


def _windows(check: LengthCheck) -> str:
    if check.windows == 0:
        return "None read"
    parts = [f"{n:,} {_WINDOWS[label]}" for label, n in check.counts.items()]
    return f"{check.windows:,}: {', '.join(parts)}"


def _dna(check: LengthCheck) -> tuple[Fact, ...]:
    ns = check.ns_in_window
    return (
        Fact(label="Windows of the reference protein", value=_windows(check)),
        Fact(
            label="Unknown bases in the window",
            value=NOT_READ if ns is None else f"{ns:,}",
        ),
        Fact(label="At a contig end", value=YES_NO[check.at_contig_edge]),
    )


def _screen(screen: LengthScreen) -> tuple[Fact, ...]:
    ratio = screen.ratio
    return (
        Fact(
            label="Model" if len(screen.genes) == 1 else "Models",
            value=listed(screen.genes),
        ),
        Fact(label="Reference gene", value=known(screen.reference_gene)),
        Fact(
            label="Ortholog group median",
            value=f"{screen.group_median:g} residues over {screen.organisms:,} organisms",
        ),
        Fact(
            label="Length against the median",
            value=NOT_READ if ratio is None else f"{ratio:g}",
        ),
    )


def _pseudogene(result: PseudogeneCallAudit) -> tuple[Fact, ...]:
    return (
        Fact(
            label="Reference coding sequence",
            value=f"{result.reference_cds_length:,} bases",
        ),
        Fact(
            label="Strain sequence rebuilt through it",
            value=f"{result.strain_cds_length:,} bases",
        ),
        Fact(
            label="Bases that match the reference",
            value=f"{result.covered:,} of {result.reference_cds_length:,}",
        ),
        Fact(
            label="Stops inside the rebuilt protein",
            value=_positions(result.premature_stops),
        ),
        Fact(
            label="Amino acids that differ from the reference",
            value=f"{result.residue_differences:,}",
        ),
        *unread_facts(result.evidence_unread),
    )


def _selenoprotein(result: SelenoproteinEndAudit) -> tuple[Fact, ...]:
    identity = result.tail_identity
    return (
        Fact(
            label="Residues the genome encodes after the model's end",
            value=result.after_model_end,
        ),
        Fact(
            label="The reference's last residues (U is selenocysteine)",
            value=result.reference_tail,
        ),
        Fact(
            label="Identity of the two ends",
            value=NOT_READ if identity is None else f"{round(100 * identity)}%",
        ),
        Fact(
            label="The model's stop sits where the reference has selenocysteine",
            value=YES_NO[result.sec_aligned],
        ),
        *unread_facts(result.evidence_unread),
    )


def _length(result: GeneLengthAudit) -> tuple[Fact, ...]:
    return (
        *_screen(result),
        *_dna(result),
        Fact(
            label="Genetic code",
            value=code_text(result.code, inferred=result.code_inferred),
        ),
        *unread_facts(result.evidence_unread),
    )


def _fusion(result: GeneFusionAudit) -> tuple[Fact, ...]:
    fusion = result.fusion
    merged = result.merged
    found = (
        ()
        if fusion is None
        else (
            Fact(label="Extra residues", value=runs_text(fusion.extra)),
            Fact(
                label="Windows matching a neighbour",
                value=f"{fusion.neighbour_windows:,} of {fusion.extra_windows:,}",
            ),
            Fact(
                label="Partner gene",
                value=NONE if fusion.partner is None else fusion.partner,
            ),
            Fact(label="Neighbours read", value=listed(fusion.neighbours)),
            Fact(label="Product", value=fusion.product),
            Fact(label="Partner's ortholog group", value=known(fusion.partner_group)),
            Fact(label="Partner's product", value=known(fusion.partner_product)),
            Fact(
                label="Partner's copies in the group",
                value=NOT_READ
                if fusion.partner_copies is None
                else listed(fusion.partner_copies),
            ),
        )
    )
    joined = (
        ()
        if merged is None
        else (
            Fact(
                label="Merged model",
                value=f"{merged.gene} on {merged.seqid}, bases {merged.start:,} to "
                f"{merged.end:,}",
            ),
        )
    )
    return (*_screen(result), *found, *joined, *unread_facts(result.evidence_unread))


def _relatives(result: StrainModelAudit) -> str:
    relatives = result.relatives
    if not relatives.members:
        missing = relatives.missing
        return NONE if missing is None else f"None: {_NO_RELATIVES[missing]}"
    return listed([f"{m.organism} ({residues(m.length)})" for m in relatives.members])


def _strain(result: StrainModelAudit) -> tuple[Fact, ...]:
    relatives = result.relatives
    median = relatives.median
    tier = relatives.tier
    not_read = result.not_read
    why = (
        ()
        if not_read is None
        else (Fact(label="Why the genome was not read", value=_NOT_READ[not_read]),)
    )
    return (
        Fact(
            label=f"Strain model {result.strain_gene}",
            value=residues(result.strain_length),
        ),
        Fact(
            label=f"Reference model {result.reference_gene}",
            value=residues(result.reference_length),
        ),
        Fact(
            label="Reference residues the strain model lacks",
            value=runs_text(result.lost),
        ),
        Fact(
            label="Strain residues the reference lacks", value=runs_text(result.extra)
        ),
        Fact(
            label="The strain's DNA over the lost part",
            value=LENGTH_SENTENCES[result.dna.verdict],
        ),
        *_dna(result.dna),
        *why,
        Fact(label="Related genomes", value=_relatives(result)),
        Fact(
            label="Related genomes from",
            value=NOT_READ if tier is None else _TIERS[tier],
        ),
        Fact(
            label="Median of the related genomes",
            value=NOT_READ if median is None else f"{median:g} residues",
        ),
        Fact(label="Paralogs near the model", value=listed(result.nearby_paralogs)),
        Fact(
            label="Genetic code",
            value=code_text(result.code, inferred=result.code_inferred),
        ),
        *unread_facts(result.evidence_unread),
    )


def _located(result: MissingGeneAudit) -> str:
    located = result.located
    if located is None:
        return NOT_READ
    found = f"{located.found:,} of {located.windows:,} windows"
    if located.span is None:
        return found
    start, end = located.span
    return f"{found}, bases {start:,} to {end:,}"


def _missing(result: MissingGeneAudit) -> tuple[Fact, ...]:
    anchors = result.anchors
    frame = result.open_frame
    stops = result.stops
    overlapping = result.overlapping
    members = result.annotated_members
    return (
        Fact(
            label="Gene looked for",
            value=f"{result.example_gene}, {residues(result.example_length)}",
        ),
        Fact(label="Genome it is absent from", value=result.absent_organism),
        Fact(
            label="Conserved neighbours",
            value="None found"
            if anchors is None
            else f"{anchors.left.gene} and {anchors.right.gene} on "
            f"{anchors.left.sequence_id}",
        ),
        Fact(label="Where the DNA encodes it", value=_located(result)),
        Fact(
            label="Open reading frame there",
            value=NOT_READ
            if frame is None
            else f"{residues(frame.length)}, {frame.identical:,} identical to the gene "
            "looked for",
        ),
        Fact(
            label="Stops in the frame",
            value=NOT_READ if stops is None else _positions(stops),
        ),
        Fact(label="The frame is whole", value=YES_NO[result.intact_frame]),
        Fact(
            label="Models annotated there",
            value=NOT_READ
            if overlapping is None
            else listed([f"{gene.gene} ({gene.product})" for gene in overlapping]),
        ),
        Fact(
            label="Members of its group annotated in the genome",
            value=NOT_READ
            if members is None
            else listed([f"{m.gene} on {m.sequence_id}" for m in members]),
        ),
        Fact(
            label="Genetic code",
            value=code_text(result.code, inferred=result.code_inferred),
        ),
    )


def _organelle(result: OrganelleGeneAudit) -> tuple[Fact, ...]:
    whole = result.reference_length
    return (
        Fact(
            label="Sequence",
            value=f"{result.sequence_id}, {result.contig_length:,} bases",
        ),
        Fact(
            label="Best whole copy on the linear sequence",
            value=f"{result.best_linear:,} of {whole:,} residues",
        ),
        Fact(
            label="Best copy across the join",
            value=f"{result.best_circular:,} of {whole:,} residues",
        ),
        Fact(
            label="Bases the two ends share",
            value=f"{result.overlap_bases:,}, with {result.overlap_mismatches:,} mismatches",
        ),
        Fact(
            label="Genetic code",
            value=code_text(result.code, inferred=result.code_inferred),
        ),
    )


def _targeted_facts(
    confirmation: FusionConfirmation
    | StrainConfirmation
    | MissingGeneConfirmation
    | OrganelleConfirmation
    | IntronConfirmation,
) -> tuple[Fact, ...]:
    match confirmation:
        case FusionConfirmation(result=result):
            return _fusion(result)
        case StrainConfirmation(result=result):
            return _strain(result)
        case MissingGeneConfirmation(result=result):
            return _missing(result)
        case OrganelleConfirmation(result=result):
            return _organelle(result)
        case IntronConfirmation(result=result):
            return intron_facts(result)


def confirmation_facts(confirmation: Confirmation) -> tuple[Fact, ...]:
    match confirmation:
        case PseudogeneConfirmation(result=result):
            return _pseudogene(result)
        case SelenoproteinConfirmation(result=result):
            return _selenoprotein(result)
        case LengthConfirmation(result=result):
            return _length(result)
        case (
            FusionConfirmation()
            | StrainConfirmation()
            | MissingGeneConfirmation()
            | OrganelleConfirmation()
            | IntronConfirmation()
        ):
            return _targeted_facts(confirmation)


def evidence_facts(payload: EvidencePayload) -> EvidenceFacts:
    match payload:
        case ConfirmationEvidence(confirmation=confirmation):
            return EvidenceFacts(
                kind="confirmation", facts=confirmation_facts(confirmation)
            )
        case RelativesEvidence():
            return EvidenceFacts(kind="relatives", facts=relatives_facts(payload))
        case GeneEvidencePayload():
            return EvidenceFacts(
                kind="gene_evidence", facts=gene_evidence_facts(payload)
            )
