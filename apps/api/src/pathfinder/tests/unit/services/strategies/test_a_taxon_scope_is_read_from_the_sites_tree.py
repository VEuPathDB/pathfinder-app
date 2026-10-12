"""The commit's organism check reads the site's organism tree when two scopes
differ by name, so a taxon meets the organisms the tree holds under it."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import COMBINE_SEARCH_NAME, CombineOp, StrategyStepNode
from veupathdb.wdk import WDKSearch

from pathfinder.services.strategies import organism_params
from pathfinder.services.strategies.organism_params import (
    organism_taxa,
    tree_cross_organism_refusal,
)

_TAXON_SEARCH = "GenesByTaxon"
_BOVIS = "Babesia bovis T2Bo"
_PARVA = "Theileria parva strain Muguga"


def _entry(term: str, *children: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"term": term, "display": term}, "children": list(children)}


# The piroplasmadb organism tree, cut to one family and one genus.
_DEFINITION = WDKSearch.model_validate(
    {
        "urlSegment": _TAXON_SEARCH,
        "parameters": [
            {
                "name": "organism",
                "type": "multi-pick-vocabulary",
                "displayType": "treeBox",
                "properties": {
                    "organismProperties": ["pruneNodesWithSingleExtendingChild"]
                },
                "vocabulary": _entry(
                    "@@fake@@",
                    _entry("Babesiidae", _entry(_BOVIS)),
                    _entry("Theileria", _entry(_PARVA)),
                ),
            }
        ],
    }
)


def _taxon(step_id: str, organism: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=_TAXON_SEARCH,
        parameters={"organism": MultiPickValue(values=[organism])},
    )


def _intersect(left: StrategyStepNode, right: StrategyStepNode) -> StrategyStepNode:
    return StrategyStepNode(
        id="both",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=left,
        secondary_input=right,
    )


@pytest.fixture
def definitions_read(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Serve the taxon search's definition and count each read of it."""
    read: list[str] = []

    async def _listed_under(site_id: str, search_name: str, record_type: str) -> str:
        del site_id, search_name
        return record_type

    async def _definition(site_id: str, record_type: str, name: str) -> WDKSearch:
        del site_id, record_type
        read.append(name)
        return _DEFINITION

    async def _marked(site_id: str, record_type: str, name: str) -> str:
        del site_id, record_type, name
        return "organism"

    monkeypatch.setattr(organism_params, "resolve_search_record_type", _listed_under)
    monkeypatch.setattr(organism_params, "read_search_definition", _definition)
    monkeypatch.setattr(organism_params, "organism_parameter", _marked)
    return read


async def test_the_tree_gives_the_organisms_under_each_entry(
    definitions_read: list[str],
) -> None:
    taxa = await organism_taxa(
        "piroplasmadb", "transcript", {_TAXON_SEARCH: "organism"}
    )

    assert taxa == {
        "Babesiidae": frozenset({_BOVIS}),
        "Theileria": frozenset({_PARVA}),
    }
    assert definitions_read == [_TAXON_SEARCH]


async def test_a_family_meets_an_organism_under_it(definitions_read: list[str]) -> None:
    root = _intersect(_taxon("family", "Babesiidae"), _taxon("strain", _BOVIS))

    refusal = await tree_cross_organism_refusal("piroplasmadb", "transcript", root)

    assert (refusal, definitions_read) == (None, [_TAXON_SEARCH])


async def test_a_family_does_not_meet_an_organism_outside_it(
    definitions_read: list[str],
) -> None:
    root = _intersect(_taxon("family", "Babesiidae"), _taxon("strain", _PARVA))

    refusal = await tree_cross_organism_refusal("piroplasmadb", "transcript", root)

    assert refusal == (
        f"Cannot INTERSECT steps with different organism scopes (Babesiidae vs "
        f"{_PARVA}). Gene IDs from different organisms never match, so this "
        f"always returns 0 results. Scope every seed to one organism: Babesiidae "
        f"or {_PARVA}."
    )


async def test_scopes_that_share_a_name_read_no_tree(
    definitions_read: list[str],
) -> None:
    root = _intersect(_taxon("one", _BOVIS), _taxon("other", _BOVIS))

    refusal = await tree_cross_organism_refusal("piroplasmadb", "transcript", root)

    assert (refusal, definitions_read) == (None, [])
