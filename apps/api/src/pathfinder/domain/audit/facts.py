from __future__ import annotations

from collections.abc import Iterable, Sequence

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from veupathdb_mcp.audit import GeneEvidence, GeneticCode, RelativeTier

from pathfinder.domain.audit.findings import (
    EvidenceKind,
    GeneEvidencePayload,
    RelativesEvidence,
)
from pathfinder.domain.audit.words import SIDE_SENTENCES

NOT_READ = "Not read"
NONE = "None found"
YES_NO: dict[bool | None, str] = {True: "Yes", False: "No", None: NOT_READ}
TIER_WORDS: dict[RelativeTier, str] = {
    "SAME_GENUS": "The same genus",
    "OTHER_GENERA": "Other genera",
}

_CODES: dict[GeneticCode, str] = {
    GeneticCode.STANDARD: "Standard",
    GeneticCode.CTG_SERINE: "CTG read as serine",
    GeneticCode.UGA_TRYPTOPHAN: "UGA read as tryptophan",
    GeneticCode.YEAST_MITOCHONDRIAL: "Yeast mitochondrial",
    GeneticCode.INVERTEBRATE_MITOCHONDRIAL: "Invertebrate mitochondrial",
}
CODE_WORDS: dict[str, dict[str, str]] = {
    GeneticCode.__name__: {code.value: words for code, words in _CODES.items()},
    "RelativeTier": {str(tier): words for tier, words in TIER_WORDS.items()},
}


class Fact(CamelModel):
    model_config = ConfigDict(frozen=True)

    label: str
    value: str


class EvidenceFacts(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: EvidenceKind
    facts: tuple[Fact, ...]


def listed(items: Sequence[str]) -> str:
    if not items:
        return NONE
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def runs_text(runs: Sequence[tuple[int, int]]) -> str:
    return listed([f"{first:,} to {last:,}" for first, last in runs])


def known(value: str | None) -> str:
    return NOT_READ if value is None else value


def counted(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def residues(n: int | None) -> str:
    return NOT_READ if n is None else counted(n, "residue", "residues")


def code_text(code: GeneticCode | None, *, inferred: bool) -> str:
    if code is None:
        return NOT_READ
    return f"{_CODES[code]} (inferred)" if inferred else _CODES[code]


def unread_facts(reasons: Sequence[str]) -> tuple[Fact, ...]:
    return (
        (Fact(label="Evidence not read", value="; ".join(reasons)),) if reasons else ()
    )


def _read_relatives(evidence: RelativesEvidence) -> tuple[Fact, ...]:
    lengths = evidence.relative_lengths
    tier = evidence.relatives_tier
    if tier is None:
        return ()
    genomes = counted(len(lengths), "genome", "genomes")
    span = f"{min(lengths.values()):,} to {max(lengths.values()):,} residues"
    return (
        Fact(label="Related genomes read", value=f"{genomes}, {span}"),
        Fact(label="Related genomes from", value=TIER_WORDS[tier]),
    )


def relatives_facts(evidence: RelativesEvidence) -> tuple[Fact, ...]:
    organism = evidence.reference_organism
    gene = (
        evidence.reference_gene
        if organism is None
        else f"{evidence.reference_gene} in {organism}"
    )
    median = evidence.relatives_median
    side = evidence.side
    reference = evidence.reference_length
    length = "length not read" if reference is None else residues(reference)
    return (
        Fact(label="Reference model", value=f"{gene}, {length}"),
        Fact(label="This model", value=residues(evidence.model_length)),
        Fact(
            label="Median of independent related genomes",
            value=NOT_READ if median is None else f"{median:g} residues",
        ),
        *_read_relatives(evidence),
        Fact(
            label="Which model the related genomes support",
            value=NOT_READ if side is None else SIDE_SENTENCES[side],
        ),
    )


def _structures(record: GeneEvidence) -> str:
    folds = [
        f"AlphaFold {fold.uniprot_id} covers residues {fold.first:,} to {fold.last:,} "
        f"of {fold.length:,}"
        for fold in record.alphafold
    ]
    similar = counted(len(record.pdb_hits), "PDB similarity", "PDB similarities")
    return "; ".join([similar, *(folds or ["no AlphaFold model"])])


def _peptides(record: GeneEvidence) -> str:
    if not record.peptides:
        return NONE
    spectra = sum(peptide.spectra for peptide in record.peptides)
    return (
        f"{counted(len(record.peptides), 'peptide', 'peptides')}, "
        f"{counted(spectra, 'spectrum', 'spectra')}"
    )


def _citations(record: GeneEvidence) -> str:
    return ", ".join(
        [
            counted(record.pubmed, "PubMed article", "PubMed articles"),
            counted(record.comments, "comment", "comments"),
            counted(record.notes, "note", "notes"),
        ]
    )


def gene_evidence_facts(payload: GeneEvidencePayload) -> tuple[Fact, ...]:
    return tuple(
        fact
        for gene, record in zip(payload.genes, payload.evidence, strict=True)
        for fact in (
            Fact(label=f"{gene} citations", value=_citations(record)),
            Fact(label=f"{gene} structures", value=_structures(record)),
            Fact(label=f"{gene} peptides", value=_peptides(record)),
        )
    )


def evidence_summary(groups: Iterable[EvidenceFacts]) -> str:
    return "; ".join(
        f"{fact.label}: {fact.value}" for group in groups for fact in group.facts
    )
