from __future__ import annotations

from pathfinder.ai.lead.intent import UserIntent
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.domain.audit.words import CHECK_TITLES


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_classification_names_every_audit_check_as_an_audit() -> None:
    described = UserIntent.model_json_schema()["properties"]["classification"]

    assert _flat(described["description"]).endswith(
        "gene_model_audit is a request to check the gene models of a genome or of "
        "named genes for errors, whatever its verb: pseudogene calls on intact "
        "genes; selenoproteins cut at their selenocysteine; gene length against "
        "orthologs; one gene split into two models; neighbouring genes fused into "
        "one model; strain model against its reference; genes missing from the "
        "annotation; organelle genes at the circular join; exon structure against "
        "rna-seq. Such a request is never a build, also when it names an organism "
        "and a gene class."
    )
    assert len(CHECK_TITLES) == 9


def test_the_classifier_keeps_a_check_of_gene_models_out_of_the_builds() -> None:
    doc = _flat(classify_user_intent.__doc__ or "")

    assert (
        "Any other imperative, except a check of gene models for errors, asks for "
        "a build."
    ) in doc
    assert (
        "- ``gene_model_audit``: a request to check the gene models of a genome or "
        "of named genes for errors (pseudogene calls, split or fused genes, gene "
        "length, exon structure), whatever its verb; a question about an audit's "
        "progress; or a question whether a gene's model is right. It states no "
        "requirement and becomes no strategy request, also when it names an "
        "organism and a gene class."
    ) in doc
