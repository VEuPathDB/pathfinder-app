"""Every tool outside FRAME reads a stated value by its parameter's rule."""

from __future__ import annotations

import json

import pytest
from pydantic import JsonValue, TypeAdapter
from pydantic_ai import ModelRetry, Tool
from veupathdb.domain.parameters import (
    FilterValue,
    MultiPickValue,
    NumberRange,
    ParamValue,
    StringValue,
)
from veupathdb.domain.strategy import StrategyStepNode, walk
from veupathdb.wdk import WDKParameter

from strategist.ai.agents.execution import build_execution_agent
from strategist.ai.tools.standalone import (
    strategy,
    strategy_edits,
)
from strategist.ai.tools.standalone.strategy import apply_operations, build_strategy
from strategist.ai.tools.standalone.strategy_edits import (
    replace_subtree,
    update_leaf_params,
)
from strategist.domain.strategy.operations import GraphOperation
from strategist.domain.strategy.session import StrategyGraph
from strategist.services.strategies.commit import CommitResult
from strategist.tests._support.instructions import pinned_instructions
from strategist.tests._support.record_classes import recorded_searches
from strategist.tests._support.recorded_searches import (
    serve_stated_reads,
)
from strategist.tests.unit.ai.tools._apply_operations_stubs import (
    context_and_commit,
    graph_with,
    pin_apply,
    revision_of,
)

_PF = "Plasmodium falciparum 3D7"
_VARIANTS = "GenesByVariantCharacteristics"
_TREE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
_DECLARATION: TypeAdapter[WDKParameter] = TypeAdapter(WDKParameter)
CAPTURED = "captured"
COUNTED = "counted"
READ = "read"
_AT_LEAST_SIX: JsonValue = [{"field": "total_variants", "value": {"min": 6}}]


@pytest.fixture
def stated_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_stated_reads(monkeypatch, list(recorded_searches().values()))


def _leaf(step_id: str, search_name: str) -> StrategyStepNode:
    return StrategyStepNode(id=step_id, search_name=search_name)


def _taxon_graph() -> StrategyGraph:
    return graph_with(_leaf("step_t", "GenesByTaxon"))


def _committed_ops(monkeypatch: pytest.MonkeyPatch) -> list[GraphOperation]:
    ops: list[GraphOperation] = []

    async def _commit(*, deps: object, op: GraphOperation) -> CommitResult:
        del deps
        ops.append(op)
        return CommitResult(description="applied")

    monkeypatch.setattr(strategy_edits, "apply_and_commit", _commit)
    return ops


class TestAnEditReadsNativeValues:
    async def test_a_list_for_a_multi_pick_commits_its_terms(
        self, monkeypatch: pytest.MonkeyPatch, stated_reads: None
    ) -> None:
        ops = _committed_ops(monkeypatch)
        ctx, _ = context_and_commit(_taxon_graph(), [])

        await update_leaf_params(ctx, "step_t", {"organism": [_PF]})

        assert [op.model_dump() for op in ops] == [
            {
                "kind": "updateStepParams",
                "step_id": "step_t",
                "parameters": {"organism": MultiPickValue(values=[_PF]).model_dump()},
            }
        ]

    async def test_the_typed_wrapper_is_refused_and_nothing_is_committed(
        self, monkeypatch: pytest.MonkeyPatch, stated_reads: None
    ) -> None:
        ops = _committed_ops(monkeypatch)
        ctx, _ = context_and_commit(_taxon_graph(), [])
        wrapped: JsonValue = {"type": "multi-pick-vocabulary", "values": [_PF]}

        with pytest.raises(ModelRetry, match="organism takes a list") as refused:
            await update_leaf_params(ctx, "step_t", {"organism": wrapped})

        assert "GenesByTaxon" in refused.value.message
        assert ops == []

    async def test_a_name_the_search_lacks_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, stated_reads: None
    ) -> None:
        ops = _committed_ops(monkeypatch)
        ctx, _ = context_and_commit(_taxon_graph(), [])

        with pytest.raises(ModelRetry, match="organisms"):
            await update_leaf_params(ctx, "step_t", {"organisms": [_PF]})

        assert ops == []


def _prompt_tree() -> JsonValue:
    """The tree the execution instructions show, in the shapes they state."""
    text = "\n".join(pinned_instructions(build_execution_agent()))
    shown = text.split("build_strategy(root=")[1].split("\n})\n")[0] + "\n}"
    return _TREE.validate_json(shown)


def _built(monkeypatch: pytest.MonkeyPatch) -> list[StrategyStepNode]:
    roots: list[StrategyStepNode] = []

    async def _build(
        *, deps: object, root: StrategyStepNode, description: object
    ) -> object:
        del deps, description
        roots.append(root)
        raise ModelRetry(CAPTURED)

    monkeypatch.setattr(strategy, "build_strategy_from_spec", _build)
    return roots


def _values_of(root: StrategyStepNode) -> dict[str, dict[str, ParamValue]]:
    return {n.search_name: n.parameters for n in walk(root) if n.parameters}


class TestATreeReadsNativeValues:
    async def test_the_instructions_tree_builds_with_each_value_read(
        self, monkeypatch: pytest.MonkeyPatch, stated_reads: None
    ) -> None:
        roots = _built(monkeypatch)
        ctx, _ = context_and_commit(StrategyGraph("g1", "g", "plasmodb"), [])
        args = Tool(build_strategy).function_schema.validator.validate_python(
            {"root": _prompt_tree()}
        )

        with pytest.raises(ModelRetry, match="captured"):
            await build_strategy(ctx, **args)

        values = _values_of(roots[0])
        [clause] = FilterValue.model_validate(
            values[_VARIANTS]["gene_variant_stats"].model_dump()
        ).filters
        assert values["GenesByTransmembraneDomains"]["min_tm"] == StringValue(value="2")
        assert values["GenesWithSignalPeptide"] == {
            "organism": MultiPickValue(values=[_PF])
        }
        assert clause == NumberRange.model_validate(
            {
                "field": "total_variants",
                "type": "number",
                "isRange": True,
                "includeUnknown": False,
                "value": {"min": 6},
            }
        )

    async def test_a_wrapped_value_in_a_subtree_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, stated_reads: None
    ) -> None:
        graph = _taxon_graph()
        ctx, _ = context_and_commit(graph, [])
        args = Tool(replace_subtree).function_schema.validator.validate_python(
            {
                "step_id": "step_t",
                "new_subtree": {
                    "searchName": "GenesByTaxon",
                    "parameters": {"organism": {"type": "string", "value": _PF}},
                },
            }
        )

        with pytest.raises(ModelRetry, match="organism takes a list"):
            await replace_subtree(ctx, **args)

        assert sorted(graph.steps) == ["step_t"]

    async def test_a_batch_writes_a_number_as_the_site_reads_it(
        self, monkeypatch: pytest.MonkeyPatch, stated_reads: None
    ) -> None:
        graph = graph_with(_leaf("step_s", "GenesByNgsSnps"))
        committed: list[list[GraphOperation]] = []
        ctx, commit = context_and_commit(graph, committed)
        pin_apply(monkeypatch, commit)
        args = Tool(apply_operations).function_schema.validator.validate_python(
            {
                "base_revision": revision_of(graph),
                "operations": [
                    {
                        "kind": "updateStepParams",
                        "stepId": "step_s",
                        "parameters": {"MinPercentMinorAlleles": 5.0},
                    }
                ],
            }
        )

        await apply_operations(ctx, **args)

        assert [op.model_dump() for op in committed[0]] == [
            {
                "kind": "updateStepParams",
                "step_id": "step_s",
                "parameters": {
                    "MinPercentMinorAlleles": StringValue(value="5").model_dump()
                },
            }
        ]

    async def test_a_batch_reads_a_leaf_it_adds_by_that_leafs_search(
        self, monkeypatch: pytest.MonkeyPatch, stated_reads: None
    ) -> None:
        graph = _taxon_graph()
        committed: list[list[GraphOperation]] = []
        ctx, commit = context_and_commit(graph, committed)
        pin_apply(monkeypatch, commit)
        args = Tool(apply_operations).function_schema.validator.validate_python(
            {
                "base_revision": revision_of(graph),
                "operations": [
                    {
                        "kind": "addLeaf",
                        "step": {
                            "id": "step_p",
                            "searchName": "GenesWithSignalPeptide",
                        },
                        "attach": {"mode": "new-root"},
                    },
                    {
                        "kind": "updateStepParams",
                        "stepId": "step_p",
                        "parameters": {"signalp_version": "SignalP-6.0"},
                    },
                ],
            }
        )

        await apply_operations(ctx, **args)

        assert [op.kind for op in committed[0]] == ["addLeaf", "updateStepParams"]


def test_the_batch_schema_shows_no_typed_wrapper() -> None:
    schema = json.dumps(Tool(apply_operations).function_schema.json_schema)

    assert [
        kind for kind in ("multi-pick-vocabulary", "MultiPickValue") if kind in schema
    ] == []


@pytest.mark.parametrize(
    "operation",
    [
        {
            "kind": "addCombine",
            "step": {
                "id": "step_c",
                "operator": "UNION",
                "searchName": "GenesByTaxon",
                "parameters": {
                    "organism": {"type": "multi-pick-vocabulary", "values": [_PF]}
                },
            },
            "leftId": "step_t",
            "rightId": "step_t",
        },
        {
            "kind": "updateStepParams",
            "stepId": "step_t",
            "parameters": {
                "organism": {"type": "multi-pick-vocabulary", "values": [_PF]}
            },
        },
    ],
)
async def test_a_batch_operation_carrying_the_wrapper_is_refused(
    monkeypatch: pytest.MonkeyPatch, stated_reads: None, operation: JsonValue
) -> None:
    graph = _taxon_graph()
    committed: list[list[GraphOperation]] = []
    ctx, commit = context_and_commit(graph, committed)
    pin_apply(monkeypatch, commit)
    args = Tool(apply_operations).function_schema.validator.validate_python(
        {"base_revision": revision_of(graph), "operations": [operation]}
    )

    with pytest.raises(ModelRetry, match="organism takes a list"):
        await apply_operations(ctx, **args)

    assert committed == []
