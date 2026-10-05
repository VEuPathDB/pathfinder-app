"""A search that marks no organism parameter runs on the organisms of its dataset,
so an INTERSECT of it with another species is refused like any other."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, walk

from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.organism_scope import (
    dataset_organisms_of,
    output_organisms,
)
from pathfinder.domain.strategy.validate import (
    cross_organism_refusal,
    first_cross_organism_refusal,
)
from pathfinder.tests._support.bound_values import bound

from ._builders import combine

_UKMEL1 = "Cryptosporidium meleagridis strain UKMEL1"
_HOMINIS = "Cryptosporidium hominis TU502"
_PARVUM = "Cryptosporidium parvum Iowa II"
_HM1 = "Entamoeba histolytica HM-1:IMSS"
# Two of the organisms of the plasmodb dataset that GenesByBindingSiteFeature runs on.
_PF = "Plasmodium falciparum 3D7"
_PV = "Plasmodium vivax P01"
# Dataset searches as cryptodb and amoebadb publish them, each named by one dataset.
_OOCYSTS = "GenesByRNASeqchomTU502_Widmer_oocysts_ebi_rnaSeq_RSRCPercentile"
_LIPPUNER = "GenesByRNASeqcparIowaII_Lippuner_rnaSeq_RSRCPercentile"
_TROPHOZOITES = (
    "GenesByRNASeqehisHM1IMSS_Trophozoite_transcriptome_ebi_rnaSeq_RSRCPercentile"
)

_MARKED = {
    "GenesWithSignalPeptide": "organism",
    "GenesByGoTerm": "organism",
    "GenesByOrthologs": "organism",
}
_TREU927 = "Trypanosoma brucei brucei TREU927"
_LVP_AGWG = "Aedes aegypti LVP_AGWG"
_PROCYCLIC = "GenesByRNASeqtbruTREU927_Naguleswaran_procyclic_ebi_rnaSeq_RSRC"
_ANTENNAE = "GenesByRNASeqaaegLVP_AGWG_SRP171130_ebi_rnaSeq_RSRCPercentile"
# The organisms of the one dataset each dataset search runs on.
_DATASET_ORGANISMS = {
    _OOCYSTS: frozenset({_HOMINIS}),
    _LIPPUNER: frozenset({_PARVUM}),
    _TROPHOZOITES: frozenset({_HM1}),
    _PROCYCLIC: frozenset({_TREU927}),
    _ANTENNAE: frozenset({_LVP_AGWG}),
}

_PREAMBLE = (
    "Cannot INTERSECT steps with different organism scopes "
    "({primary} vs {secondary}). Gene IDs from different organisms never match, "
    "so this always returns 0 results. "
)


def _datasets(root: StrategyStepNode) -> dict[str, frozenset[str]]:
    """The organisms of the dataset each step of the tree runs on, by step id."""
    return {
        node.id: _DATASET_ORGANISMS[node.search_name]
        for node in walk(root)
        if node.search_name in _DATASET_ORGANISMS
    }


def _marked(step_id: str, search_name: str, organism: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=search_name,
        parameters={"organism": MultiPickValue(values=[organism])},
    )


def _dataset_step(step_id: str, search_name: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=search_name,
        parameters={"min_expression_percentile": StringValue(value="80")},
    )


class TestTheScopeOfAStep:
    def test_a_search_that_marks_no_organism_has_its_datasets(self) -> None:
        step = _dataset_step("p", _OOCYSTS)

        assert output_organisms(step, _MARKED, _datasets(step)) == {_HOMINIS}

    def test_without_its_dataset_the_scope_is_unknown(self) -> None:
        step = _dataset_step("p", _OOCYSTS)

        assert [
            output_organisms(step, _MARKED, {}),
            output_organisms(step, _MARKED, _datasets(step)),
        ] == [None, {_HOMINIS}]

    def test_a_transform_that_marks_an_organism_states_the_scope(self) -> None:
        step = StrategyStepNode(
            id="t",
            search_name="GenesByOrthologs",
            parameters={"organism": MultiPickValue(values=[_UKMEL1])},
            primary_input=_dataset_step("p", _OOCYSTS),
        )

        assert output_organisms(step, _MARKED, _datasets(step)) == {_UKMEL1}

    def test_a_transform_that_marks_none_keeps_the_datasets(self) -> None:
        step = StrategyStepNode(
            id="t",
            search_name="GenesByWeightFilter",
            primary_input=_dataset_step("p", _OOCYSTS),
        )

        assert output_organisms(step, _MARKED, _datasets(step)) == {_HOMINIS}


def _criterion(
    criterion_id: str,
    search_name: str,
    organism_param: str | None,
    organisms: list[str],
) -> Criterion:
    return Criterion(
        id=criterion_id,
        text=criterion_id,
        search_name=search_name,
        organism_param=organism_param,
        dataset_organisms=organisms,
        resolved_params=bound({"organism": MultiPickValue(values=[_UKMEL1])}),
    )


class TestTheDatasetsOfTheCriteria:
    def test_only_a_search_that_marks_no_organism_reads_its_dataset(self) -> None:
        criteria = [
            _criterion("c_oocysts", _OOCYSTS, None, [_HOMINIS]),
            _criterion("c_sites", "GenesByBindingSiteFeature", "organism", [_PF, _PV]),
            _criterion("c_signal", "GenesWithSignalPeptide", "organism", []),
            _criterion("c_text", "GenesByText", None, []),
        ]

        assert dataset_organisms_of(criteria) == {"c_oocysts": frozenset({_HOMINIS})}


class TestAnIntersectWithADatasetSearch:
    def test_another_species_is_refused_with_the_transform_of_its_side(self) -> None:
        root = combine(
            "c",
            _marked("s", "GenesWithSignalPeptide", _UKMEL1),
            _dataset_step("p", _OOCYSTS),
        )

        assert cross_organism_refusal(root, root, _MARKED, _datasets(root)) == (
            _PREAMBLE.format(primary=_UKMEL1, secondary=_HOMINIS)
            + f"The {_OOCYSTS} search runs on an experiment of {_HOMINIS}, and no "
            f"parameter changes that organism. Map that side to {_UKMEL1} with a "
            f"GenesByOrthologs transform."
        )

    def test_the_same_organism_is_not_refused(self) -> None:
        go_term = _marked("g", "GenesByGoTerm", _HM1)
        trophozoites = _dataset_step("p", _TROPHOZOITES)
        root = combine("c", go_term, trophozoites)

        assert [
            output_organisms(go_term, _MARKED, _datasets(root)),
            output_organisms(trophozoites, _MARKED, _datasets(root)),
            cross_organism_refusal(root, root, _MARKED, _datasets(root)),
        ] == [{_HM1}, {_HM1}, None]

    def test_two_experiments_of_two_species_map_one_side(self) -> None:
        root = combine("c", _dataset_step("a", _OOCYSTS), _dataset_step("b", _LIPPUNER))

        assert cross_organism_refusal(root, root, _MARKED, _datasets(root)) == (
            _PREAMBLE.format(primary=_HOMINIS, secondary=_PARVUM)
            + "Each side runs on an experiment, and no parameter changes its "
            "organism. Map one side to the organism of the other with a "
            "GenesByOrthologs transform."
        )

    def test_a_tree_read_without_datasets_abstains(self) -> None:
        oocysts = _dataset_step("p", _OOCYSTS)
        root = combine("c", _marked("s", "GenesWithSignalPeptide", _UKMEL1), oocysts)

        assert [
            output_organisms(oocysts, _MARKED, {}),
            cross_organism_refusal(root, root, _MARKED, {}),
        ] == [None, None]


def _amoebadb() -> StrategyStepNode:
    return combine(
        "c", _marked("g", "GenesByGoTerm", _HM1), _dataset_step("p", _TROPHOZOITES)
    )


def _tritrypdb() -> StrategyStepNode:
    return combine(
        "c", _marked("g", "GenesByGoTerm", _TREU927), _dataset_step("f", _PROCYCLIC)
    )


def _vectorbase() -> StrategyStepNode:
    expressed = combine(
        "c",
        _marked("i", "GenesByInterproDomain", _LVP_AGWG),
        _dataset_step("female", _ANTENNAE),
    )
    return combine("m", expressed, _dataset_step("male", _ANTENNAE), CombineOp.MINUS)


@pytest.mark.parametrize(
    ("tree", "leaves"),
    [
        (_amoebadb, [{_HM1}, {_HM1}]),
        (_tritrypdb, [{_TREU927}, {_TREU927}]),
        (_vectorbase, [{_LVP_AGWG}, {_LVP_AGWG}, {_LVP_AGWG}]),
    ],
)
def test_a_dataset_search_on_the_organism_of_its_partner_builds(
    tree: Callable[[], StrategyStepNode], leaves: list[set[str]]
) -> None:
    marked = {**_MARKED, "GenesByInterproDomain": "organism"}
    root = tree()
    datasets = _datasets(root)
    scopes = [
        output_organisms(node, marked, datasets)
        for node in walk(root)
        if not node.inputs()
    ]

    assert (scopes, first_cross_organism_refusal(root, marked, datasets)) == (
        leaves,
        None,
    )
