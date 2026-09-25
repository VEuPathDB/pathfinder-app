"""Shared strategy-tree builders and the Hypothesis generators of valid trees."""

from __future__ import annotations

import string
from collections.abc import Iterable
from typing import TypeGuard

from hypothesis import HealthCheck, settings, strategies
from veupathdb.domain.parameters import (
    MultiPickValue,
    NumberValue,
    ParamValue,
    StringValue,
)
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    ColocationParams,
    CombineOp,
    StepKind,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    StructureNode,
)
from pathfinder.domain.strategy.operations import GraphOperation
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_diff import diff_specs
from pathfinder.domain.strategy.spec_hydration import spec_from_ast
from pathfinder.domain.strategy.spec_to_operations import operations_for


def leaf(step_id: str, search_name: str = "geneById") -> StrategyStepNode:
    return StrategyStepNode(id=step_id, search_name=search_name)


def combine(
    step_id: str,
    primary: StrategyStepNode,
    secondary: StrategyStepNode,
    operator: CombineOp = CombineOp.INTERSECT,
) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=COMBINE_SEARCH_NAME,
        primary_input=primary,
        secondary_input=secondary,
        operator=operator,
    )


def transform(
    step_id: str, input_: StrategyStepNode, search_name: str = "orthologs"
) -> StrategyStepNode:
    return StrategyStepNode(id=step_id, search_name=search_name, primary_input=input_)


def graph_with(
    roots: Iterable[StrategyStepNode], *, record_type: str | None = None
) -> StrategyGraph:
    graph = StrategyGraph(graph_id="g1", name="g", site_id="plasmodb")
    if record_type is not None:
        graph.record_type = record_type
    for root in roots:
        graph.steps.update(flatten_tree(root))
    graph.recompute_roots()
    return graph


_IDS = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_", min_size=1, max_size=8
)

_CANNED_PARAMS: tuple[dict[str, ParamValue], ...] = (
    {},
    {"organism": MultiPickValue(values=["Pf3D7"])},
    {"text": StringValue(value="kinase")},
)


@strategies.composite
def strategy_trees(draw: strategies.DrawFn) -> StrategyStepNode:
    """An arbitrary valid strategy tree whose step ids are unique."""
    used: set[str] = set()

    def fresh() -> str:
        while True:
            candidate = draw(_IDS)
            if candidate not in used:
                used.add(candidate)
                return candidate

    def build(depth: int) -> StrategyStepNode:
        shape = (
            draw(strategies.sampled_from(["leaf", "transform", "combine"]))
            if depth
            else "leaf"
        )
        params = draw(strategies.sampled_from(_CANNED_PARAMS))
        display = draw(strategies.one_of(strategies.none(), strategies.just("A label")))
        if shape == "leaf":
            return StrategyStepNode(
                id=fresh(),
                search_name="GenesByTaxon",
                parameters=params,
                display_name=display,
            )
        if shape == "transform":
            return StrategyStepNode(
                id=fresh(),
                search_name="orthologs",
                parameters=params,
                display_name=display,
                primary_input=build(depth - 1),
            )
        return StrategyStepNode(
            id=fresh(),
            search_name=COMBINE_SEARCH_NAME,
            display_name=display,
            operator=draw(
                strategies.sampled_from([CombineOp.INTERSECT, CombineOp.UNION])
            ),
            primary_input=build(depth - 1),
            secondary_input=build(depth - 1),
        )

    return build(draw(strategies.integers(min_value=0, max_value=3)))


_search_names = strategies.text(
    alphabet=string.ascii_lowercase + "_",
    min_size=1,
    max_size=20,
).filter(lambda s: s != COMBINE_SEARCH_NAME)

_param_values: strategies.SearchStrategy[ParamValue] = strategies.one_of(
    strategies.builds(StringValue, value=strategies.text(min_size=1, max_size=10)),
    strategies.builds(
        NumberValue, value=strategies.floats(min_value=-1000, max_value=1000)
    ),
    strategies.builds(
        MultiPickValue,
        values=strategies.lists(
            strategies.text(min_size=1, max_size=8), min_size=1, max_size=3
        ),
    ),
)

_param_dicts = strategies.dictionaries(
    keys=strategies.text(alphabet=string.ascii_lowercase, min_size=1, max_size=8),
    values=_param_values,
    max_size=3,
)

_boolean_ops = strategies.sampled_from(
    [
        CombineOp.INTERSECT,
        CombineOp.UNION,
        CombineOp.MINUS,
        CombineOp.RMINUS,
        CombineOp.LONLY,
        CombineOp.RONLY,
    ],
)

_colocation = strategies.builds(
    ColocationParams,
    operation=strategies.sampled_from(["overlaps", "contains", "is contained in"]),
    strand=strategies.sampled_from(["either strand", "same strand", "opposite strand"]),
    output=strategies.sampled_from(["a", "b"]),
    begin_offset_a=strategies.integers(min_value=0, max_value=10_000),
    end_offset_a=strategies.integers(min_value=0, max_value=10_000),
    begin_offset_b=strategies.integers(min_value=0, max_value=10_000),
    end_offset_b=strategies.integers(min_value=0, max_value=10_000),
)

_search_node = strategies.builds(
    StrategyStepNode,
    search_name=_search_names,
    parameters=_param_dicts,
)


def _transform_factory(
    child: StrategyStepNode, search_name: str, params: dict[str, ParamValue]
) -> StrategyStepNode:
    return StrategyStepNode(
        search_name=search_name, parameters=params, primary_input=child
    )


def _combine_factory(
    left: StrategyStepNode, right: StrategyStepNode, operator: CombineOp
) -> StrategyStepNode | None:
    if left.id == right.id:
        return None
    return StrategyStepNode(
        search_name=COMBINE_SEARCH_NAME,
        primary_input=left,
        secondary_input=right,
        operator=operator,
    )


def _colocate_factory(
    left: StrategyStepNode, right: StrategyStepNode, params: ColocationParams
) -> StrategyStepNode | None:
    if left.id == right.id:
        return None
    return StrategyStepNode(
        search_name=COMBINE_SEARCH_NAME,
        primary_input=left,
        secondary_input=right,
        operator=CombineOp.COLOCATE,
        colocation_params=params,
    )


def _built(node: StrategyStepNode | None) -> TypeGuard[StrategyStepNode]:
    """A factory returns None for a pair it cannot combine."""
    return node is not None


def _extend(
    children: strategies.SearchStrategy[StrategyStepNode],
) -> strategies.SearchStrategy[StrategyStepNode]:
    return strategies.one_of(
        strategies.builds(_transform_factory, children, _search_names, _param_dicts),
        strategies.builds(_combine_factory, children, children, _boolean_ops).filter(
            _built
        ),
        strategies.builds(_colocate_factory, children, children, _colocation).filter(
            _built
        ),
    )


# Every node kind, including colocation, with ids Pydantic mints.
ANY_TREE = strategies.recursive(_search_node, _extend, max_leaves=8)

PROFILE = settings(
    max_examples=120,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)

FAST_PROFILE = settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])


def text_leaf() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_text",
        search_name="GenesByText",
        display_name="protease text",
        parameters={"organism": MultiPickValue(values=["Plasmodium"])},
    )


def go_leaf() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_go",
        search_name="GenesByGoTerm",
        display_name="proteolysis GO",
        parameters={"organism": MultiPickValue(values=["Plasmodium"])},
    )


def expr_leaf() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_expr",
        search_name="GenesByRNASeqEvidence",
        display_name="top decile",
        parameters={"min_expression_percentile": NumberValue(value=90)},
    )


def tm_leaf() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_tm",
        search_name="GenesByTransmembraneDomains",
        display_name="two or more TM domains",
        parameters={"min_tm": NumberValue(value=2)},
    )


def transform_over(node: StrategyStepNode) -> StrategyStepNode:
    return StrategyStepNode(
        id="step_orth",
        search_name="GenesByOrthologs",
        display_name="P. vivax orthologs",
        parameters={"organism": MultiPickValue(values=["P. vivax P01"])},
        primary_input=node,
    )


def three_step_root() -> StrategyStepNode:
    """``((text INTERSECT go) INTERSECT expr)``."""
    return combine("step_c2", combine("step_c1", text_leaf(), go_leaf()), expr_leaf())


def graph_of(root: StrategyStepNode) -> StrategyGraph:
    graph = StrategyGraph(graph_id="g1", name="Test strategy", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    graph.last_step_id = root.id
    return graph


def spec_of(root: StrategyStepNode) -> OperationalSpec:
    ast = StrategyAst(record_type="transcript", root=root)
    return spec_from_ast(ast, goal="find proteases")


def plan(
    before: OperationalSpec, after: OperationalSpec, graph: StrategyGraph
) -> list[GraphOperation]:
    return list(operations_for(diff_specs(before, after), after=after, graph=graph))


def applied(root: StrategyStepNode, ops: list[GraphOperation]) -> StrategyGraph:
    """The live graph after the plan is applied to it."""
    graph = graph_of(root)
    for op in ops:
        apply_operation(graph, op)
    return graph


def shape(graph: StrategyGraph) -> str:
    """The boolean shape of the primary tree, naming only non-combine steps."""

    def render(step_id: str) -> str:
        step = graph.steps[step_id]
        if step.kind is StepKind.COMBINE:
            left, right = step.input_ids()
            return f"({render(left)} {step.operator} {render(right)})"
        if step.primary_input_id is not None:
            return f"{step_id}[{render(step.primary_input_id)}]"
        return step_id

    root_id = graph.primary_root_id()
    assert root_id is not None
    return render(root_id)


def spec_leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def spec_joined(operator: CombineOp, *inputs: StructureNode) -> StructureNode:
    return StructureNode(kind="combine", operator=operator, inputs=list(inputs))


def spec_transform(criterion_id: str, input_: StructureNode) -> StructureNode:
    return StructureNode(kind="transform", criterion_id=criterion_id, inputs=[input_])
