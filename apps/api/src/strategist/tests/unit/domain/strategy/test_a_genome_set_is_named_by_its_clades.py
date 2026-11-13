from __future__ import annotations

from veupathdb.domain.parameters import PhyleticTree, StringValue
from veupathdb.wdk import phyletic_tree_of

from strategist.domain.strategy.genome_set_names import (
    genome_set_name,
    required_genomes_name,
)
from strategist.domain.strategy.operational_spec import Criterion
from strategist.tests._support.bound_values import bound
from strategist.tests._support.recorded_searches import suite_search

_TREE = (
    phyletic_tree_of(
        list(suite_search("search_genes_by_ortholog_pattern").parameters or [])
    )
    or PhyleticTree()
)


def _under(clade: str) -> list[str]:
    return sorted(_TREE.genomes_under([clade]))


def test_a_set_equal_to_one_clade_is_named_by_it() -> None:
    assert genome_set_name(_TREE, _under("OOMY")) == "28 Oomycota genomes"


def test_a_set_spanning_two_clades_names_both() -> None:
    genomes = [*_under("OOMY"), *_under("COCC")]

    assert genome_set_name(_TREE, genomes) == "84 genomes in Coccidia and Oomycota"


def test_a_clade_and_a_genome_name_each() -> None:
    genomes = [*_under("OOMY"), "pfal"]

    assert genome_set_name(_TREE, genomes) == (
        "29 genomes in Plasmodium falciparum 3D7 and Oomycota"
    )


def test_a_set_of_many_clades_names_the_clades_that_span_it() -> None:
    genomes = ["tgon", "ncan", "pfal", "pber"]

    assert genome_set_name(_TREE, genomes) == (
        "4 genomes (2 of the 56 in Coccidia, 2 of the 80 in Aconoidasida)"
    )


def test_a_profile_names_the_genomes_it_requires() -> None:
    tokens = "%".join(f"{code}:Y" for code in _under("OOMY"))
    criterion = Criterion(
        id="c_profile",
        text="an ortholog in oomycetes",
        search_name="GenesByOrthologPattern",
        resolved_params=bound({"profile_pattern": StringValue(value=f"%{tokens}%")}),
    )

    assert required_genomes_name(criterion, _TREE) == "28 Oomycota genomes"
    assert required_genomes_name(criterion, None) == ""
