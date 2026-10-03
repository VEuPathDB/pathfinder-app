"""A variant's tree-parent value runs as its leaves, the way a bound criterion's does.

The site counts only the leaves of a ``countOnlyLeaves`` tree, so a parent sent
as it is selects nothing. The leaves come from the definition WDK builds from
the variant's own values, the one the bind canonicalizes against.
"""

from __future__ import annotations

import pytest
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import MultiPickValue, ParamValue, collect_leaf_terms
from veupathdb.domain.parameters.wdk_vocab import find_vocab_node
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKSearchResponse
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ResolvedSearch,
    format_param_info_typed,
)

from pathfinder.ai.tools.standalone import _variant_targets
from pathfinder.ai.tools.standalone._variant_targets import checked_variants
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.experiment import variant_comparison
from pathfinder.services.experiment.variant_comparison import (
    VariantInput,
    VariantSpec,
)
from pathfinder.tests._support.recorded_searches import suite_search

# The recorded plasmodb GenesByTaxon, whose organism is a countOnlyLeaves tree.
_TAXON = suite_search("search_genes_by_taxon")


def _leaves_of(term: str) -> list[str]:
    vocabulary = (_TAXON.parameters or [])[0].vocabulary
    node = find_vocab_node(vocabulary, term)
    assert node is not None
    return collect_leaf_terms(node)


def _resolved() -> ResolvedSearch:
    return ResolvedSearch(
        response=WDKSearchResponse.model_validate(
            {
                "searchData": _TAXON.model_dump(by_alias=True, mode="json"),
                "validation": {"level": "DISPLAYABLE", "isValid": True},
            }
        ),
        values_were_read=True,
    )


@pytest.fixture(autouse=True)
def read_with(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, ParamValue]]:
    """The values each definition read was built from."""
    reads: list[dict[str, ParamValue]] = []

    async def _parameters(
        site_id: str, record_type: str, search_name: str, context: dict[str, str]
    ) -> list[ParameterInfo]:
        del site_id, record_type, search_name, context
        return format_param_info_typed(list(_TAXON.parameters or []))

    async def _resolve(
        ctx: SearchContext,
        *,
        resolved_record_type: str,
        parameters: dict[str, ParamValue],
    ) -> ResolvedSearch:
        assert (ctx.search_name, resolved_record_type) == ("GenesByTaxon", "transcript")
        reads.append(parameters)
        return _resolved()

    monkeypatch.setattr(variant_comparison, "search_parameters", _parameters)
    monkeypatch.setattr(_variant_targets, "resolve_search_details", _resolve)
    return reads


def _variant(label: str, organism: object) -> VariantInput:
    return VariantInput.model_validate(
        {
            "label": label,
            "searchName": "GenesByTaxon",
            "parameters": {"organism": organism},
        }
    )


def _taxon_step(organism: list[str]) -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Plasmodium", site_id="plasmodb")
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_taxon",
            search_name="GenesByTaxon",
            parameters={"organism": MultiPickValue(values=organism)},
        )
    )
    graph.recompute_roots()
    session.graph = graph
    return session


async def test_a_parent_value_runs_as_its_leaves(
    read_with: list[dict[str, ParamValue]],
) -> None:
    across = _variant(
        "Across Plasmodium", {"type": "string", "value": '["Plasmodium"]'}
    )
    leaf = _variant(
        "Plasmodium falciparum 3D7",
        {"type": "multi-pick-vocabulary", "values": ["Plasmodium falciparum 3D7"]},
    )

    checked = await checked_variants(
        StrategySession(site_id="plasmodb"), [across, leaf]
    )

    leaves = _leaves_of("Plasmodium")
    assert len(leaves) > 1
    assert checked[0].parameters["organism"] == MultiPickValue(values=leaves)
    assert checked[1].parameters["organism"] == MultiPickValue(
        values=["Plasmodium falciparum 3D7"]
    )
    assert read_with[0] == {"organism": MultiPickValue(values=["Plasmodium"])}


async def test_the_leaves_the_step_holds_run_as_they_are(
    read_with: list[dict[str, ParamValue]],
) -> None:
    """The step's own value is already the bind's; it needs no second reading."""
    leaves = _leaves_of("Plasmodium")
    held = _variant("as built", {"type": "multi-pick-vocabulary", "values": leaves})
    narrowed = _variant(
        "3D7 only",
        {"type": "multi-pick-vocabulary", "values": ["Plasmodium falciparum 3D7"]},
    )

    checked = await checked_variants(_taxon_step(leaves), [held, narrowed])

    assert checked[0].parameters["organism"] == MultiPickValue(values=leaves)
    assert read_with == [
        {"organism": MultiPickValue(values=["Plasmodium falciparum 3D7"])}
    ]


async def test_a_variant_with_no_tree_value_reads_no_definition(
    read_with: list[dict[str, ParamValue]],
) -> None:
    text = VariantInput(label="no organism", search_name="GenesByTaxon", parameters={})
    listed = VariantSpec(
        label="no organism",
        search_name="GenesByTaxon",
        parameters={},
        record_type="transcript",
    )

    checked = await checked_variants(StrategySession(site_id="plasmodb"), [text, text])

    assert (checked, read_with) == ([listed, listed], [])
