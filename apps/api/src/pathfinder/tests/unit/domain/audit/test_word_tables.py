from __future__ import annotations

from pathfinder.domain.audit.confirmations import FindingVerdict
from pathfinder.domain.audit.scope import CheckName
from pathfinder.domain.audit.words import verdict_sentence

_EXPECTED: list[tuple[CheckName, FindingVerdict, str]] = [
    (
        "pseudogene_call",
        "INTACT",
        "The strain's DNA encodes the whole protein, so the pseudogene call is wrong",
    ),
    (
        "pseudogene_call",
        "FRAMESHIFT",
        "The strain's DNA has a frameshift, so the pseudogene call holds",
    ),
    (
        "pseudogene_call",
        "PREMATURE_STOP",
        "The strain's DNA has a stop inside the protein, so the pseudogene call holds",
    ),
    (
        "pseudogene_call",
        "START_OR_STOP_LOST",
        "The strain's DNA lost the start or the stop codon",
    ),
    (
        "pseudogene_call",
        "NOT_ALIGNED",
        "The strain's DNA does not align to the reference gene",
    ),
    (
        "selenoprotein_end",
        "CONTAINS_SEC",
        "The model already reads through its selenocysteine codon",
    ),
    (
        "selenoprotein_end",
        "STOPS_AT_SEC",
        "The model stops at the TGA that the reference reads as selenocysteine",
    ),
    (
        "selenoprotein_end",
        "NOT_AT_SEC",
        "The model ends, but not at a selenocysteine codon",
    ),
    (
        "selenoprotein_end",
        "MODEL_NOT_FOUND",
        "The model's end was not found in the genome",
    ),
    (
        "gene_length",
        "GENOME_ENCODES",
        "The genome's DNA encodes the part the model lacks",
    ),
    (
        "gene_length",
        "ASSEMBLY",
        "The part the model lacks falls in an assembly gap or at a contig end",
    ),
    (
        "gene_length",
        "ABSENT",
        "The genome's DNA does not encode the part the model lacks",
    ),
    ("gene_length", "NOT_SHORT", "The model is not short against its orthologs"),
    (
        "gene_length",
        "SPLIT_CONFIRMED",
        "The two models are parts of one protein, in order on one strand",
    ),
    (
        "gene_length",
        "SPLIT_UNCLEAR",
        "The DNA does not show whether the two models are one gene",
    ),
    (
        "gene_length",
        "NOT_CHECKED",
        "The site's whole ortholog group does not class the model as short, so its DNA was not read",
    ),
    (
        "gene_split",
        "GENOME_ENCODES",
        "The genome's DNA encodes the part the model lacks",
    ),
    (
        "gene_split",
        "ASSEMBLY",
        "The part the model lacks falls in an assembly gap or at a contig end",
    ),
    (
        "gene_split",
        "ABSENT",
        "The genome's DNA does not encode the part the model lacks",
    ),
    ("gene_split", "NOT_SHORT", "The model is not short against its orthologs"),
    (
        "gene_split",
        "SPLIT_CONFIRMED",
        "The two models are parts of one protein, in order on one strand",
    ),
    (
        "gene_split",
        "SPLIT_UNCLEAR",
        "The DNA does not show whether the two models are one gene",
    ),
    (
        "gene_split",
        "NOT_CHECKED",
        "The site's ortholog group does not call the pair a split, so their DNA was not read",
    ),
    (
        "gene_fusion",
        "EXTRA_MATCHES_NEIGHBOUR",
        "The extra part matches a neighbouring gene, so two genes are fused into one model",
    ),
    (
        "gene_fusion",
        "EXTRA_UNEXPLAINED",
        "The model has an extra part that matches no neighbouring gene",
    ),
    ("gene_fusion", "NO_EXTRA", "The model has no extra part"),
    ("gene_fusion", "LONG", "The gene is long against its orthologs"),
    (
        "gene_fusion",
        "SHORT",
        "The gene is short against its orthologs, so the fusion check read nothing",
    ),
    (
        "gene_fusion",
        "TYPICAL",
        "The gene has the usual length of its orthologs, so the fusion check read nothing",
    ),
    (
        "gene_fusion",
        "SPLIT",
        "The gene is one of a split pair, so the fusion check read nothing",
    ),
    (
        "gene_fusion",
        "UNQUALIFIED",
        "The ortholog group cannot class the gene's length, so the fusion check read nothing",
    ),
    (
        "strain_model",
        "STRAIN_SHORT",
        "Related genomes match the reference, so the strain model is too short",
    ),
    (
        "strain_model",
        "REFERENCE_LONG",
        "Related genomes match the strain, so the reference model is too long",
    ),
    ("strain_model", "UNCLEAR", "Related genomes do not show which model is wrong"),
    (
        "strain_model",
        "NO_RELATIVES",
        "No independent related genome can show which model is wrong",
    ),
    ("strain_model", "NOT_JUDGED", "The check did not judge which model is wrong"),
    (
        "missing_gene",
        "IN_DNA_UNANNOTATED",
        "The genome's DNA encodes the gene, and no model is annotated there",
    ),
    (
        "missing_gene",
        "IN_DNA_OTHER_MODEL",
        "The genome's DNA encodes the gene inside another model",
    ),
    ("missing_gene", "PARTIAL", "Part of the gene is encoded where it should be"),
    (
        "missing_gene",
        "GAP",
        "An assembly gap sits where the gene should be, so the check cannot judge it",
    ),
    (
        "missing_gene",
        "NOT_IN_DNA",
        "The genome's DNA does not encode the gene, so its absence is real",
    ),
    (
        "missing_gene",
        "NO_SYNTENY",
        "No conserved neighbours mark where the gene should be, so the check read no DNA",
    ),
    (
        "missing_gene",
        "ANNOTATED_IN_GENOME",
        "The genome annotates members of the gene's group, so the gene is not missing",
    ),
    (
        "organelle_join",
        "SPLIT_AT_JOIN",
        "The protein is whole only across the join of the circular genome",
    ),
    (
        "organelle_join",
        "INTACT_ON_THE_LINE",
        "The protein is whole on the linear sequence",
    ),
    (
        "organelle_join",
        "NOT_FOUND",
        "The sequence holds no whole copy of the reference protein",
    ),
    ("intron_support", "SUPPORTED", "RNA-seq reads support every annotated intron"),
    (
        "intron_support",
        "UNSUPPORTED_SHIFTED",
        "RNA-seq reads join the exons a few bases away from the annotated splice site",
    ),
    (
        "intron_support",
        "UNSUPPORTED_MISSING_EXON",
        "RNA-seq reads join an exon the model does not have",
    ),
    (
        "intron_support",
        "UNSUPPORTED_REPLACED",
        "A strongly read RNA-seq junction replaces an annotated intron that has no read",
    ),
    (
        "intron_support",
        "UNSUPPORTED_NONCANONICAL",
        "An annotated intron with no read has splice-site bases that are not GT..AG or GC..AG",
    ),
    (
        "intron_support",
        "UNSUPPORTED_RETAINED",
        "RNA-seq reads cover an annotated intron across 90% or more of its length at 25% or more of the exons' depth, and none splices it out",
    ),
    (
        "intron_support",
        "UNSUPPORTED_UNEXPLAINED",
        "An annotated intron has no RNA-seq read, and no junction, splice-site bases or coverage explains it, or that evidence could not be read",
    ),
    (
        "intron_support",
        "NOT_EXPRESSED",
        "The gene has too few RNA-seq reads to judge its introns",
    ),
    ("intron_support", "NOT_CHECKED", "The check could not read the gene's introns"),
]


def test_each_verdict_reads_its_own_sentence() -> None:
    assert [
        (check, verdict, verdict_sentence(check, verdict))
        for check, verdict, _ in _EXPECTED
    ] == _EXPECTED
