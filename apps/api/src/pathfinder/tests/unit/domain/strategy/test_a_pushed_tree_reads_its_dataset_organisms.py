"""The push validator refuses an INTERSECT of a dataset search with a search on
another species, and accepts one on the dataset's own organism."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.domain.strategy.validate import validate_strategy

from ._builders import combine

_OOCYSTS = "GenesByRNASeqchomTU502_Widmer_oocysts_ebi_rnaSeq_RSRCPercentile"
_HOMINIS = "Cryptosporidium hominis TU502"
_UKMEL1 = "Cryptosporidium meleagridis strain UKMEL1"
_MARKED = {"GenesWithSignalPeptide": "organism"}
_DATASETS = {_OOCYSTS: frozenset({_HOMINIS})}


def _intersect(organism: str) -> StrategyStepNode:
    signal = StrategyStepNode(
        id="signal",
        search_name="GenesWithSignalPeptide",
        parameters={"organism": MultiPickValue(values=[organism])},
    )
    oocysts = StrategyStepNode(id="oocysts", search_name=_OOCYSTS, parameters={})
    return combine("both", signal, oocysts)


def test_another_species_is_refused_at_the_push() -> None:
    result = validate_strategy(_intersect(_UKMEL1), "transcript", _MARKED, _DATASETS)

    assert [e.code for e in result.errors] == ["CROSS_ORGANISM_INTERSECT"]


def test_the_datasets_own_organism_is_accepted_at_the_push() -> None:
    result = validate_strategy(_intersect(_HOMINIS), "transcript", _MARKED, _DATASETS)

    assert result.errors == []
