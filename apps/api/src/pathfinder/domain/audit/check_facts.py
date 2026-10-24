from __future__ import annotations

from collections.abc import Sequence

from veupathdb_mcp.audit import (
    MissingGeneAudit,
    OrganelleGeneAudit,
    PseudogeneCallAudit,
    SelenoproteinEndAudit,
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
    listed,
    relatives_facts,
    residues,
    unread_facts,
)
from pathfinder.domain.audit.findings import (
    ConfirmationEvidence,
    EvidencePayload,
    GeneEvidencePayload,
    RelativesEvidence,
)
from pathfinder.domain.audit.intron_facts import intron_facts
from pathfinder.domain.audit.length_facts import (
    fusion_facts,
    length_facts,
    strain_facts,
)
from pathfinder.domain.audit.words import percent

_LISTED_STOPS = 20


def _positions(at: Sequence[int]) -> str:
    if not at:
        return NONE
    word = "residue" if len(at) == 1 else "residues"
    return f"at {word} {listed([f'{n:,}' for n in at])}"


def _stops(at: Sequence[int]) -> str:
    shown = _positions(at)
    return f"{shown} (the first {_LISTED_STOPS})" if len(at) >= _LISTED_STOPS else shown


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
            value=_stops(result.premature_stops),
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
            value=NOT_READ if identity is None else percent(identity),
        ),
        Fact(
            label="The model's stop sits where the reference has selenocysteine",
            value=YES_NO[result.sec_aligned],
        ),
        *unread_facts(result.evidence_unread),
    )


def _located(result: MissingGeneAudit) -> str:
    located = result.located
    if located is None:
        return NOT_READ
    found = f"{located.found:,} of {located.windows:,} parts of the gene"
    if located.span is None:
        return found
    start, end = located.span
    return f"{found}, bases {start:,} to {end:,}"


def _anchors(result: MissingGeneAudit) -> str:
    anchors = result.anchors
    if anchors is not None:
        return (
            f"{anchors.left.gene} and {anchors.right.gene} on "
            f"{anchors.left.sequence_id}"
        )
    return NONE if result.verdict == "NO_SYNTENY" else NOT_READ


def _missing(result: MissingGeneAudit) -> tuple[Fact, ...]:
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
        Fact(label="Conserved neighbours", value=_anchors(result)),
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
            value=f"{result.overlap_bases:,}, with {result.overlap_mismatches:,} "
            "mismatches",
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
            return fusion_facts(result)
        case StrainConfirmation(result=result):
            return strain_facts(result)
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
            return length_facts(result)
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
