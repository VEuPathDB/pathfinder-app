"""A pushed tree reads the dataset organisms of the searches that mark no
organism parameter, and a tree with no INTERSECT or transform reads none."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import COMBINE_SEARCH_NAME, CombineOp, StrategyStepNode

from pathfinder.services.strategies import organism_params
from pathfinder.services.strategies.organism_params import tree_dataset_organisms

_OOCYSTS = "GenesByRNASeqchomTU502_Widmer_oocysts_ebi_rnaSeq_RSRCPercentile"
_HOMINIS = "Cryptosporidium hominis TU502"


def _leaf(step_id: str, search_name: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=search_name,
        parameters={"organism": MultiPickValue(values=[_HOMINIS])},
    )


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    read: list[str] = []

    async def _datasets(site_id: str, search_name: str) -> list[str]:
        del site_id
        read.append(search_name)
        return [_HOMINIS] if search_name == _OOCYSTS else []

    monkeypatch.setattr(organism_params, "dataset_organisms", _datasets)
    return read


async def test_only_a_search_that_marks_no_organism_is_read(asked: list[str]) -> None:
    root = StrategyStepNode(
        id="both",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=_leaf("signal", "GenesWithSignalPeptide"),
        secondary_input=_leaf("oocysts", _OOCYSTS),
    )

    found = await tree_dataset_organisms(
        "cryptodb", root, {"GenesWithSignalPeptide": "organism"}
    )

    assert found == {_OOCYSTS: frozenset({_HOMINIS})}
    assert asked == [_OOCYSTS]


async def test_a_tree_with_no_intersect_reads_nothing(asked: list[str]) -> None:
    root = StrategyStepNode(
        id="union",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.UNION,
        primary_input=_leaf("signal", "GenesWithSignalPeptide"),
        secondary_input=_leaf("oocysts", _OOCYSTS),
    )

    assert await tree_dataset_organisms("cryptodb", root, {}) == {}
    assert asked == []
