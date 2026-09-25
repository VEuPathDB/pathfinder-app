"""The review VERIFY returns: one row per stated requirement, a capped sample of
the genes, and the sources it cites."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.domain.evidence import (
    SAMPLED_GENE_LIMIT,
    Citation,
    RequirementCheck,
    SampledGene,
    VerificationReview,
)


def _gene(gene_id: str, fits: str, why: str = "product names a kinase") -> SampledGene:
    return SampledGene.model_validate(
        {
            "geneId": gene_id,
            "product": "protein kinase",
            "organism": "Plasmodium falciparum 3D7",
            "fits": fits,
            "why": why,
        }
    )


def test_a_met_requirement_names_what_answers_it() -> None:
    with pytest.raises(ValidationError, match="a met requirement names"):
        RequirementCheck(
            text="with a signal peptide",
            turn=1,
            answered_by=[],
            how="search",
            status="met",
        )


def test_an_unmet_requirement_may_name_nothing() -> None:
    row = RequirementCheck(
        text="expressed in gametocytes",
        turn=2,
        how="search",
        status="unmet",
        note="no step reads gametocyte expression",
    )

    assert row.model_dump(by_alias=True) == {
        "text": "expressed in gametocytes",
        "turn": 2,
        "answeredBy": [],
        "how": "search",
        "status": "unmet",
        "note": "no step reads gametocyte expression",
    }


def test_the_sample_holds_at_most_the_limit() -> None:
    genes = [_gene(f"PF3D7_{i:07d}", "yes") for i in range(SAMPLED_GENE_LIMIT + 1)]

    with pytest.raises(ValidationError, match="at most 8 items"):
        VerificationReview(sampled_genes=genes)


def test_only_genes_that_do_not_fit_make_the_counted_caveat() -> None:
    mixed = VerificationReview(
        sampled_genes=[
            _gene("PF3D7_0100100", "yes"),
            _gene("PF3D7_0100200", "no", "product is a histone, no kinase domain"),
            _gene("PF3D7_0100300", "unclear", "product is hypothetical"),
            _gene("PF3D7_0100400", "no", "product is a ribosomal protein"),
        ]
    )
    fitting = VerificationReview(sampled_genes=[_gene("PF3D7_0100100", "yes")])

    assert (mixed.misfit_caveat(), fitting.misfit_caveat()) == (
        (
            "2 of 4 sampled genes do not fit: `PF3D7_0100200` (product is a "
            "histone, no kinase domain); `PF3D7_0100400` (product is a ribosomal "
            "protein)"
        ),
        None,
    )


def test_the_rows_a_reply_must_name_are_the_unmet_and_the_unexpressed() -> None:
    met = RequirementCheck(
        text="P. falciparum 3D7",
        turn=1,
        answered_by=["s1"],
        how="parameter",
        status="met",
    )
    unmet = RequirementCheck(text="A or B", turn=1, how="structure", status="unmet")
    unexpressed = RequirementCheck(
        text="orthologs", turn=2, how="search", status="unexpressed"
    )

    review = VerificationReview(requirements=[met, unmet, unexpressed])

    assert review.to_report() == [unmet, unexpressed]
    assert review.unmet() == [unmet]


def test_a_citation_is_checked_by_every_identifier_it_carries() -> None:
    cited = Citation(
        kind="literature",
        label="Signal peptides in P. falciparum",
        doi="10.1038/nature12970",
        pmid="24463516",
        why="lists the exported kinases",
    )

    assert cited.references() == ["10.1038/nature12970", "24463516"]


def test_the_review_lists_every_text_a_reader_can_see() -> None:
    review = VerificationReview(
        requirements=[
            RequirementCheck(
                text="with a signal peptide",
                turn=1,
                answered_by=["s1"],
                how="search",
                status="met",
                note="GenesWithSignalPeptide",
            )
        ],
        sampled_genes=[_gene("PF3D7_0100100", "yes")],
        sources=[
            Citation(
                kind="web",
                label="SignalP",
                url="https://services.healthtech.dtu.dk/signalp",
                why="defines the predictor",
            )
        ],
    )

    assert review.texts() == [
        "with a signal peptide",
        "GenesWithSignalPeptide",
        "protein kinase",
        "Plasmodium falciparum 3D7",
        "product names a kinase",
        "SignalP",
        "defines the predictor",
        "https://services.healthtech.dtu.dk/signalp",
    ]


def test_a_citation_carries_an_identifier_a_reader_can_open() -> None:
    with pytest.raises(ValidationError, match="a url, a DOI or a PMID"):
        Citation(kind="web", label="A page", why="it says so")
