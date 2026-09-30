"""A variant's tree-parent value runs as its leaves, the way a bound criterion's does.

The site counts only the leaves of a ``countOnlyLeaves`` tree, so a parent sent
as it is selects nothing.
"""

from __future__ import annotations

import pytest
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import MultiPickValue, collect_leaf_terms
from veupathdb.domain.parameters.wdk_vocab import find_vocab_node
from veupathdb.wdk import WDKSearchResponse
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.ai.tools.standalone import _variant_targets
from pathfinder.ai.tools.standalone._variant_targets import checked_variants
from pathfinder.services.experiment import variant_comparison
from pathfinder.services.experiment.variant_comparison import VariantSpec
from pathfinder.tests._support.recorded_searches import suite_search

# The recorded plasmodb GenesByTaxon, whose organism is a countOnlyLeaves tree.
_TAXON = suite_search("search_genes_by_taxon")


def _leaves_of(term: str) -> list[str]:
    vocabulary = (_TAXON.parameters or [])[0].vocabulary
    node = find_vocab_node(vocabulary, term)
    assert node is not None
    return collect_leaf_terms(node)


def _response() -> WDKSearchResponse:
    return WDKSearchResponse.model_validate(
        {
            "searchData": _TAXON.model_dump(by_alias=True, mode="json"),
            "validation": {"level": "DISPLAYABLE", "isValid": True},
        }
    )


@pytest.fixture(autouse=True)
def _catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _parameters(
        site_id: str, record_type: str, search_name: str, context: dict[str, str]
    ) -> list[ParameterInfo]:
        del site_id, record_type, search_name, context
        return format_param_info_typed(list(_TAXON.parameters or []))

    async def _details(ctx: SearchContext) -> tuple[WDKSearchResponse, str]:
        assert ctx.search_name == "GenesByTaxon"
        return _response(), "transcript"

    monkeypatch.setattr(variant_comparison, "search_parameters", _parameters)
    monkeypatch.setattr(_variant_targets, "fetch_search_details", _details)


def _variant(label: str, organism: object) -> VariantSpec:
    return VariantSpec.model_validate(
        {
            "label": label,
            "searchName": "GenesByTaxon",
            "parameters": {"organism": organism},
        }
    )


async def test_a_parent_value_runs_as_its_leaves() -> None:
    across = _variant(
        "Across Plasmodium", {"type": "string", "value": '["Plasmodium"]'}
    )
    leaf = _variant(
        "Plasmodium falciparum 3D7",
        {"type": "multi-pick-vocabulary", "values": ["Plasmodium falciparum 3D7"]},
    )

    checked = await checked_variants("plasmodb", [across, leaf])

    leaves = _leaves_of("Plasmodium")
    assert len(leaves) > 1
    assert checked[0].parameters["organism"] == MultiPickValue(values=leaves)
    assert checked[1].parameters["organism"] == MultiPickValue(
        values=["Plasmodium falciparum 3D7"]
    )


async def test_a_variant_with_no_tree_value_reads_no_definition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _never(ctx: SearchContext) -> tuple[WDKSearchResponse, str]:
        raise AssertionError(ctx.search_name)

    monkeypatch.setattr(_variant_targets, "fetch_search_details", _never)
    text = VariantSpec(
        label="no organism",
        search_name="GenesByTaxon",
        parameters={},
    )

    assert await checked_variants("plasmodb", [text, text]) == [text, text]
