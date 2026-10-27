"""The review of one check: the checks on the site, a capped sample of the
genes, and the sources it cites."""

from __future__ import annotations

from pathfinder.domain.citations import (
    Citation,
)
from pathfinder.domain.evidence import (
    SAMPLED_GENE_LIMIT,
    SampledGene,
    VerificationReview,
)
from pathfinder.domain.site_checks import SiteCheck
from pathfinder.domain.strategy.constraints import ConstraintKind


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


def test_the_sample_holds_at_most_the_limit() -> None:
    genes = [_gene(f"PF3D7_{i:07d}", "yes") for i in range(SAMPLED_GENE_LIMIT + 1)]

    assert (
        VerificationReview(sampled_genes=genes).sampled_genes
        == genes[:SAMPLED_GENE_LIMIT]
    )


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
        checks=[
            SiteCheck(
                kind=ConstraintKind.OTHER,
                subject="with a signal peptide",
                status="unchecked",
                evidence="no check reads this requirement on the site",
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
        "no check reads this requirement on the site",
        "protein kinase",
        "Plasmodium falciparum 3D7",
        "product names a kinase",
        "SignalP",
        "defines the predictor",
        "https://services.healthtech.dtu.dk/signalp",
    ]


def test_a_citation_carries_an_identifier_a_reader_can_open() -> None:
    assert Citation(kind="web", label="A page", why="it says so").references() == []
