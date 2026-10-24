from __future__ import annotations

from collections.abc import Mapping

from veupathdb_mcp.audit import (
    RETAINED_MIN_COVERED,
    RETAINED_MIN_SHARE,
    FusionVerdict,
    IntronVerdict,
    LengthClass,
    LengthVerdict,
    MissingVerdict,
    OrganelleVerdict,
    PseudogeneVerdict,
    SecVerdict,
    SideVerdict,
)

from pathfinder.domain.audit.confirmations import FindingVerdict
from pathfinder.domain.audit.findings import ErrorType, FindingStatus
from pathfinder.domain.audit.scope import CheckName
from pathfinder.domain.audit.verdicts import (
    LiteratureStatus,
    ReviewAgreement,
    ReviewStatus,
    VerdictKind,
)


def percent(share: float) -> str:
    return f"{round(100 * share)}%"


CHECK_TITLES: dict[CheckName, str] = {
    "pseudogene_call": "Pseudogene calls on intact genes",
    "selenoprotein_end": "Selenoproteins cut at their selenocysteine",
    "gene_length": "Gene length against orthologs",
    "gene_split": "One gene split into two models",
    "gene_fusion": "Neighbouring genes fused into one model",
    "strain_model": "Strain model against its reference",
    "missing_gene": "Genes missing from the annotation",
    "organelle_join": "Organelle genes at the circular join",
    "intron_support": "Exon structure against RNA-seq",
}

_INTRON: dict[IntronVerdict, str] = {
    "SUPPORTED": "RNA-seq reads support every annotated intron",
    "UNSUPPORTED_SHIFTED": (
        "RNA-seq reads join the exons a few bases away from the annotated splice site"
    ),
    "UNSUPPORTED_MISSING_EXON": "RNA-seq reads join an exon the model does not have",
    "UNSUPPORTED_REPLACED": (
        "A strongly read RNA-seq junction replaces an annotated intron that has no read"
    ),
    "UNSUPPORTED_NONCANONICAL": (
        "An annotated intron with no read has splice-site bases that are not "
        "GT..AG or GC..AG"
    ),
    "UNSUPPORTED_RETAINED": (
        f"RNA-seq reads cover an annotated intron across {percent(RETAINED_MIN_COVERED)} "
        f"or more of its length at {percent(RETAINED_MIN_SHARE)} or more of the exons' "
        "depth, and none splices it out"
    ),
    "UNSUPPORTED_UNEXPLAINED": (
        "An annotated intron has no RNA-seq read, and no junction, splice-site bases "
        "or coverage explains it, or that evidence could not be read"
    ),
    "NOT_EXPRESSED": "The gene has too few RNA-seq reads to judge its introns",
    "NOT_CHECKED": "The check could not read the gene's introns",
}
_PSEUDOGENE: dict[PseudogeneVerdict, str] = {
    "INTACT": "The strain's DNA encodes the whole protein, so the pseudogene call is wrong",
    "FRAMESHIFT": "The strain's DNA has a frameshift, so the pseudogene call holds",
    "PREMATURE_STOP": (
        "The strain's DNA has a stop inside the protein, so the pseudogene call holds"
    ),
    "START_OR_STOP_LOST": "The strain's DNA lost the start or the stop codon",
    "NOT_ALIGNED": "The strain's DNA does not align to the reference gene",
}
_SELENOPROTEIN: dict[SecVerdict, str] = {
    "CONTAINS_SEC": "The model already reads through its selenocysteine codon",
    "STOPS_AT_SEC": (
        "The model stops at the TGA that the reference reads as selenocysteine"
    ),
    "NOT_AT_SEC": "The model ends, but not at a selenocysteine codon",
    "MODEL_NOT_FOUND": "The model's end was not found in the genome",
}
LENGTH_SENTENCES: dict[LengthVerdict, str] = {
    "GENOME_ENCODES": "The genome's DNA encodes the part the model lacks",
    "ASSEMBLY": (
        "The part the model lacks falls in an assembly gap or at a contig end"
    ),
    "ABSENT": "The genome's DNA does not encode the part the model lacks",
    "NOT_SHORT": "The model is not short against its orthologs",
    "SPLIT_CONFIRMED": (
        "The two models are parts of one protein, in order on one strand"
    ),
    "SPLIT_UNCLEAR": "The DNA does not show whether the two models are one gene",
    "NOT_CHECKED": (
        "The site's whole ortholog group does not class the model as short, so its "
        "DNA was not read"
    ),
}
_FUSION: dict[LengthClass | FusionVerdict, str] = {
    "EXTRA_MATCHES_NEIGHBOUR": (
        "The extra part matches a neighbouring gene, so two genes are fused into "
        "one model"
    ),
    "EXTRA_UNEXPLAINED": (
        "The model has an extra part that matches no neighbouring gene"
    ),
    "NO_EXTRA": "The model has no extra part",
    "LONG": "The gene is long against its orthologs",
    "SHORT": (
        "The gene is short against its orthologs, so the fusion check read nothing"
    ),
    "TYPICAL": (
        "The gene has the usual length of its orthologs, so the fusion check read "
        "nothing"
    ),
    "SPLIT": "The gene is one of a split pair, so the fusion check read nothing",
    "UNQUALIFIED": (
        "The ortholog group cannot class the gene's length, so the fusion check "
        "read nothing"
    ),
}
SIDE_SENTENCES: dict[SideVerdict, str] = {
    "STRAIN_SHORT": (
        "Related genomes match the reference, so the strain model is too short"
    ),
    "REFERENCE_LONG": (
        "Related genomes match the strain, so the reference model is too long"
    ),
    "UNCLEAR": "Related genomes do not show which model is wrong",
    "NO_RELATIVES": "No independent related genome can show which model is wrong",
    "NOT_JUDGED": "The check did not judge which model is wrong",
}
_MISSING: dict[MissingVerdict, str] = {
    "IN_DNA_UNANNOTATED": (
        "The genome's DNA encodes the gene, and no model is annotated there"
    ),
    "IN_DNA_OTHER_MODEL": "The genome's DNA encodes the gene inside another model",
    "PARTIAL": "Part of the gene is encoded where it should be",
    "GAP": (
        "An assembly gap sits where the gene should be, so the check cannot judge it"
    ),
    "NOT_IN_DNA": ("The genome's DNA does not encode the gene, so its absence is real"),
    "NO_SYNTENY": (
        "No conserved neighbours mark where the gene should be, so the check read "
        "no DNA"
    ),
    "ANNOTATED_IN_GENOME": (
        "The genome annotates members of the gene's group, so the gene is not missing"
    ),
}
_ORGANELLE: dict[OrganelleVerdict, str] = {
    "SPLIT_AT_JOIN": "The protein is whole only across the join of the circular genome",
    "INTACT_ON_THE_LINE": "The protein is whole on the linear sequence",
    "NOT_FOUND": "The sequence holds no whole copy of the reference protein",
}


_SPLIT: dict[LengthVerdict, str] = {
    **LENGTH_SENTENCES,
    "NOT_CHECKED": (
        "The site's ortholog group does not call the pair a split, so their DNA was "
        "not read"
    ),
}


def _by_name[K: FindingVerdict](
    check: CheckName, table: Mapping[K, str]
) -> dict[tuple[CheckName, FindingVerdict], str]:
    return {(check, verdict): sentence for verdict, sentence in table.items()}


_SENTENCES: dict[tuple[CheckName, FindingVerdict], str] = {
    **_by_name("pseudogene_call", _PSEUDOGENE),
    **_by_name("selenoprotein_end", _SELENOPROTEIN),
    **_by_name("gene_length", LENGTH_SENTENCES),
    **_by_name("gene_split", _SPLIT),
    **_by_name("gene_fusion", _FUSION),
    **_by_name("strain_model", SIDE_SENTENCES),
    **_by_name("missing_gene", _MISSING),
    **_by_name("organelle_join", _ORGANELLE),
    **_by_name("intron_support", _INTRON),
}

ERROR_TYPE_TITLES: dict[ErrorType, str] = {
    "intact_gene_called_pseudogene": "Intact gene called a pseudogene",
    "sec_read_as_stop": "Selenocysteine codon read as a stop",
    "truncated_model": "Model too short",
    "split_model": "One gene split into two models",
    "over_extended_model": "Model too long",
    "fused_model": "Two genes fused into one model",
    "missing_gene": "Gene missing from the annotation",
    "organelle_split_at_join": "Organelle gene split at the circular join",
    "missing_exon": "Exon missing from the model",
    "shifted_splice_site": "Splice site shifted",
    "spurious_intron": "Intron the RNA-seq does not splice",
    "unsupported_intron": "Intron with no RNA-seq support",
}

ERROR_TYPE_DESCRIPTIONS: dict[ErrorType, str] = {
    "intact_gene_called_pseudogene": (
        "The site calls the gene a pseudogene, but the genome's DNA encodes the "
        "whole protein its reference encodes."
    ),
    "sec_read_as_stop": (
        "The model stops at a TGA codon that the gene reads as selenocysteine, so "
        "the protein it states is cut short."
    ),
    "truncated_model": (
        "The model's protein is shorter than its orthologs', and the genome's DNA "
        "encodes the part it lacks."
    ),
    "split_model": (
        "Two neighbouring models are parts of one protein, in order on one strand."
    ),
    "over_extended_model": (
        "The model's protein is longer than its orthologs', and no ortholog holds "
        "the extra part."
    ),
    "fused_model": "One model holds the proteins of two neighbouring genes.",
    "missing_gene": (
        "The genome's DNA encodes a gene its relatives have, and no model is "
        "annotated there."
    ),
    "organelle_split_at_join": (
        "The organelle genome is circular but stored as a line, and the gene is "
        "cut where the line ends."
    ),
    "missing_exon": "RNA-seq reads join an exon the model does not have.",
    "shifted_splice_site": (
        "RNA-seq reads join the exons at another site than the model's: a few "
        "bases away, or by a junction that replaces the annotated intron."
    ),
    "spurious_intron": (
        "The model splices out a stretch the RNA-seq reads keep: its splice-site "
        "bases are not canonical, or reads cover it across its length."
    ),
    "unsupported_intron": (
        "The model has an intron no RNA-seq read supports, and no junction or "
        "coverage explains it."
    ),
}

VERDICT_KIND_SENTENCES: dict[VerdictKind, str] = {
    "error": "The review keeps the error",
    "no_error": "The review finds no error",
    "undecided": "The review could not decide",
}

LITERATURE_SENTENCES: dict[LiteratureStatus, str] = {
    "known": "Already reported",
    "not_found": "No report of it was found",
    "not_searched": "The literature was not searched",
}

REVIEW_STATUS_SENTENCES: dict[ReviewStatus, str] = {
    "waiting": "Reviews are queued",
    "reviewing": "Reviewing findings",
    "synthesized": "Reviewed and summarized",
    "stopped": "Reviews stopped",
}

UNCHECKED_SENTENCES: dict[FindingStatus, str] = {
    "screened": "Not checked yet",
    "unsampled": "Not checked: not in the random sample",
    "trying": "Being checked",
    "confirmed": "Checked",
    "failed": "Not checked: the check failed",
    "declined": "Not checked: the check does not take this target",
    "unreached": "Not checked: the site did not answer",
    "unread": "Not checked: not read before the run's deadline",
}


def agreement_sentence(agreement: ReviewAgreement) -> str:
    if agreement.sampled == 0:
        return (
            "No finding was reviewed twice, so the reviews' agreement is not measured"
        )
    share = round(100 * agreement.agreed / agreement.sampled)
    return (
        f"Two independent reviews agreed on {agreement.agreed} of "
        f"{agreement.sampled} sampled findings ({share}%)"
    )


def paper_sentence(*, depends: bool | None) -> str:
    match depends:
        case True:
            return "A published study depends on this gene's model"
        case False:
            return "No published study was found that depends on this gene's model"
        case None:
            return "Not checked whether a published study depends on this gene's model"


def verdict_sentence(check: CheckName, verdict: FindingVerdict) -> str:
    return _SENTENCES[check, verdict]
