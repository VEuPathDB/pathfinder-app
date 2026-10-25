from __future__ import annotations

from pathfinder.domain.audit.scope import (
    GenePairTarget,
    MissingGeneTarget,
    SingleGeneTarget,
)
from pathfinder.domain.audit.words import target_words, verdict_sentence

_PAIR = GenePairTarget(
    check="pseudogene_call", genes=("PfNF54_140028700:pseudogene", "PF3D7_1423800")
)


def test_a_target_is_named_by_its_check_title_and_its_genes_as_written() -> None:
    assert target_words(_PAIR) == (
        "Pseudogene calls on intact genes, PfNF54_140028700:pseudogene and "
        "PF3D7_1423800"
    )
    assert _PAIR.key == "pseudogene_call:PfNF54_140028700%3Apseudogene+PF3D7_1423800"


def test_a_single_gene_target_names_its_one_gene() -> None:
    target = SingleGeneTarget(check="intron_support", genes=("NCU00776",))

    assert target_words(target) == "Exon structure against RNA-seq, NCU00776"


def test_a_target_with_a_genome_names_it() -> None:
    target = MissingGeneTarget(
        check="missing_gene",
        genes=("TGARI_257090",),
        absent_organism="Toxoplasma gondii GT1",
    )

    assert target_words(target) == (
        "Genes missing from the annotation, TGARI_257090 in Toxoplasma gondii GT1"
    )


def test_a_verdict_code_has_its_sentence() -> None:
    assert verdict_sentence("pseudogene_call", "PREMATURE_STOP") == (
        "The strain's DNA has a stop inside the protein, so the pseudogene call holds"
    )
