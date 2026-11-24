from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue

from strategist.ai.tools.standalone._frame_proposals import CriterionCall
from strategist.ai.tools.standalone._frame_values import _siblings_judged_again
from strategist.domain.strategy.named_taxa import organism_trees
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
)
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.recorded_searches import client_search

_SEARCH = "GenesByTaxon"
_PF3D7 = "Plasmodium falciparum 3D7"
_PVP01 = "Plasmodium vivax P01"
_MESSAGE = f"Compare {_PF3D7} versus {_PVP01} kinases."


def test_the_first_side_is_stated_once_the_second_side_binds() -> None:
    definition = client_search("search_genes_by_taxon")
    trees = organism_trees(definition)
    [organism] = list(trees)
    first = Criterion(
        id="c_pf",
        text=f"{_PF3D7} genes",
        search_name=_SEARCH,
        resolved_params={
            organism: BoundValue(value=MultiPickValue(values=[_PF3D7]), source="chosen")
        },
        measurements=[
            Measurement(kind="vocabulary_label", param=organism, label=_PF3D7)
        ],
    )
    second = {
        organism: BoundValue(value=MultiPickValue(values=[_PVP01]), source="chosen")
    }

    draft = _siblings_judged_again(
        OperationalSpec(criteria=[first]),
        CriterionCall(
            criterion_id="c_pv", search_name=_SEARCH, text=f"{_PVP01} genes", params={}
        ),
        second,
        infos=sheet_of(definition.parameters or []),
        trees=trees,
        request_texts=[_MESSAGE],
    )

    [held] = draft.criteria
    assert (
        held.resolved_params[organism].source,
        held.resolved_params[organism].basis,
    ) == (
        "stated",
        _PF3D7,
    )
