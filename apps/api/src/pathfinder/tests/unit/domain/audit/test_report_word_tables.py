from __future__ import annotations

from pathfinder.domain.audit.words import (
    CHECK_TITLES,
    ERROR_TYPE_DESCRIPTIONS,
    ERROR_TYPE_TITLES,
    HALT_SENTENCES,
    LITERATURE_SENTENCES,
    REVIEW_STATUS_SENTENCES,
    UNCHECKED_SENTENCES,
    UNRESOLVED_WORDS,
    VERDICT_KIND_SENTENCES,
)


def test_the_check_titles_table_reads_its_exact_words() -> None:
    assert CHECK_TITLES == {
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


def test_the_error_type_titles_table_reads_its_exact_words() -> None:
    assert ERROR_TYPE_TITLES == {
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


def test_the_error_type_descriptions_table_reads_its_exact_words() -> None:
    assert ERROR_TYPE_DESCRIPTIONS == {
        "intact_gene_called_pseudogene": "The site calls the gene a pseudogene, but the genome's DNA encodes the whole protein its reference encodes.",
        "sec_read_as_stop": "The model stops at a TGA codon that the gene reads as selenocysteine, so the protein it states is cut short.",
        "truncated_model": "The model's protein is shorter than its orthologs', and the genome's DNA encodes the part it lacks.",
        "split_model": "Two neighbouring models are parts of one protein, in order on one strand.",
        "over_extended_model": "The model's protein is longer than its orthologs', and no ortholog holds the extra part.",
        "fused_model": "One model holds the proteins of two neighbouring genes.",
        "missing_gene": "The genome's DNA encodes a gene its relatives have, and no model is annotated there.",
        "organelle_split_at_join": "The organelle genome is circular but stored as a line, and the gene is cut where the line ends.",
        "missing_exon": "RNA-seq reads join an exon the model does not have.",
        "shifted_splice_site": "RNA-seq reads join the exons at another site than the model's: a few bases away, or by a junction that replaces the annotated intron.",
        "spurious_intron": "The model splices out a stretch the RNA-seq reads keep: its splice-site bases are not canonical, or reads cover it across its length.",
        "unsupported_intron": "The model has an intron no RNA-seq read supports, and no junction or coverage explains it.",
    }


def test_the_verdict_kind_sentences_table_reads_its_exact_words() -> None:
    assert VERDICT_KIND_SENTENCES == {
        "error": "The review keeps the error",
        "no_error": "The review finds no error",
        "undecided": "The review could not decide",
    }


def test_the_literature_sentences_table_reads_its_exact_words() -> None:
    assert LITERATURE_SENTENCES == {
        "known": "Already reported",
        "not_found": "No report of it was found",
        "not_searched": "The literature was not searched",
    }


def test_the_review_status_sentences_table_reads_its_exact_words() -> None:
    assert REVIEW_STATUS_SENTENCES == {
        "waiting": "Reviews are queued",
        "reviewing": "Reviewing findings",
        "synthesized": "Reviewed and summarized",
        "stopped": "Reviews stopped",
    }


def test_the_unchecked_sentences_table_reads_its_exact_words() -> None:
    assert UNCHECKED_SENTENCES == {
        "screened": "Not checked yet",
        "unsampled": "Not checked: not in the random sample",
        "trying": "Being checked",
        "confirmed": "Checked",
        "failed": "Not checked: the check failed",
        "declined": "Not checked: the check does not take this target",
        "unreached": "Not checked: the site did not answer",
        "unread": "Not checked: not read before the run's deadline",
    }


def test_the_halt_sentences_table_reads_its_exact_words() -> None:
    assert HALT_SENTENCES == {
        "sign_in": (
            "The audit needs your VEuPathDB sign-in. Sign in on the site, then "
            "resume it."
        ),
        "task_failed": (
            "The audit task stopped on an error. Resume it to go on from the last "
            "unit it finished."
        ),
    }


def test_the_unresolved_words_table_reads_its_exact_words() -> None:
    assert UNRESOLVED_WORDS == {
        "screened": "not checked yet",
        "unsampled": "not in the random sample",
        "trying": "being checked",
        "failed": "where the check failed",
        "declined": "that the check does not take",
        "unreached": "where the site did not answer",
        "unread": "not read before the run's deadline",
    }
