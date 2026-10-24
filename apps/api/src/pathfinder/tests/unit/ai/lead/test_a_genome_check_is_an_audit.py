from __future__ import annotations

from pathfinder.ai.lead.intent import UserIntent
from pathfinder.ai.lead.lead_tools import classify_user_intent


def _flat(text: str) -> str:
    return " ".join(text.split())


def _classification() -> str:
    described = UserIntent.model_json_schema()["properties"]["classification"]
    return _flat(described["description"])


def test_the_classification_names_every_audit_check_as_an_audit() -> None:
    assert _classification().endswith(
        "gene_model_audit is a request to check the gene models of a genome or of "
        "named genes for errors, whatever its verb: pseudogene calls on intact "
        "genes; selenoproteins cut at their selenocysteine; gene length against "
        "orthologs; one gene split into two models; neighbouring genes fused into "
        "one model; strain model against its reference; genes missing from the "
        "annotation; organelle genes at the circular join; exon structure against "
        "RNA-seq. A request to find or list genes by a property of their models "
        'asks for no error check and is a build: "Find pseudogenes in P. '
        'falciparum NF54" and "List genes longer than 10 kb in 3D7" are '
        "new_strategy."
    )


def test_the_classification_never_calls_an_organism_and_a_class_an_audit() -> None:
    assert "names an organism and a gene class" not in _classification()


def test_the_classifier_defines_an_audit_once_in_the_field() -> None:
    doc = _flat(classify_user_intent.__doc__ or "")

    assert (
        "Any other imperative asks for a build, except a ``gene_model_audit`` as "
        "the ``classification`` field defines it."
    ) in doc
    assert (
        "- ``gene_model_audit``: an audit request as the ``classification`` field "
        "defines it, a question about an audit's progress, or a question whether "
        "a gene's model is right. It states no requirement and becomes no "
        "strategy request."
    ) in doc
    assert "pseudogene calls" not in doc
