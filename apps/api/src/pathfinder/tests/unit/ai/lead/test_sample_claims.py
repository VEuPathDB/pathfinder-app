"""A count of sampled genes that fit, stated in prose, is held to the sample the
check judged."""

from __future__ import annotations

import pytest

from pathfinder.ai.lead.evidence_claims import sample_claims, unbacked_sample_claims
from pathfinder.domain.evidence import GeneFit, SampledGene


def _gene(gene_id: str, fits: GeneFit) -> SampledGene:
    return SampledGene(
        gene_id=gene_id,
        product="protein kinase",
        organism="Plasmodium falciparum 3D7",
        fits=fits,
        why="the product names a kinase",
    )


_SAMPLE = [
    *(_gene(f"PF3D7_010{i}000", "yes") for i in range(6)),
    _gene("PF3D7_0106000", "no"),
    _gene("PF3D7_0107000", "no"),
]


@pytest.mark.parametrize(
    "prose",
    [
        "**6** of 8 sampled genes fit the request.",
        "2 of the 8 sampled genes do not fit.",
        "6/8 sampled genes fit.",
    ],
)
def test_a_count_the_sample_holds_is_backed(prose: str) -> None:
    assert unbacked_sample_claims(sample_claims(prose), _SAMPLE) == []


def test_all_is_refused_with_the_count_the_sample_holds() -> None:
    prose = "All 8 sampled genes fit the request."

    assert unbacked_sample_claims(sample_claims(prose), _SAMPLE) == [
        (
            "The reply says all 8 sampled genes fit; the check sampled 8 genes: "
            "6 fit, 2 do not fit (`PF3D7_0106000`, `PF3D7_0107000`), 0 unclear."
        )
    ]


def test_a_count_with_no_sample_behind_it_is_refused() -> None:
    prose = "All sampled genes fit."

    assert unbacked_sample_claims(sample_claims(prose), []) == [
        "The reply says all sampled genes fit, and no check sampled a gene."
    ]


def test_prose_that_counts_no_sampled_genes_claims_nothing() -> None:
    assert sample_claims("The strategy returns 212 genes; 8 were read.") == []
