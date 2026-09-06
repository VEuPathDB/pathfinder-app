"""Shared builder helpers for test data construction."""

from dataclasses import dataclass

from veupathdb.domain.parameters.specs import ParamSpecNormalized
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.graph_model import StrategyStep
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.session import StrategyGraph


@dataclass
class ParamSpecConfig:
    """Configuration for the param spec builder."""

    name: str = "test_param"
    param_type: str = "string"
    allow_empty: bool = False
    min_selected: int | None = None
    max_selected: int | None = None
    vocabulary: dict | list | None = None
    count_only_leaves: bool = False
    is_number: bool = False
    min: float | None = None
    max: float | None = None
    increment: float | None = None
    max_length: int | None = None


# ---------------------------------------------------------------------------
# StrategyStepNode builders
# ---------------------------------------------------------------------------


def make_leaf(
    step_id: str,
    name: str = "GenesByTextSearch",
    display: str | None = None,
    parameters: dict | None = None,
) -> StrategyStepNode:
    """Create a leaf (search) StrategyStepNode."""
    return StrategyStepNode(
        search_name=name,
        parameters=parameters if parameters is not None else {},
        display_name=display,
        id=step_id,
    )


def make_combine(
    step_id: str,
    left: StrategyStepNode,
    right: StrategyStepNode,
    operator: CombineOp = CombineOp.INTERSECT,
) -> StrategyStepNode:
    """Create a combine (boolean) StrategyStepNode."""
    return StrategyStepNode(
        search_name="BooleanQuestion",
        parameters={},
        primary_input=left,
        secondary_input=right,
        operator=operator,
        id=step_id,
    )


def make_transform(
    step_id: str,
    input_step: StrategyStepNode,
    name: str = "GenesByOrthologs",
    parameters: dict | None = None,
) -> StrategyStepNode:
    """Create a transform (unary) StrategyStepNode."""
    return StrategyStepNode(
        search_name=name,
        parameters=parameters if parameters is not None else {"organism": "Pf3D7"},
        primary_input=input_step,
        id=step_id,
    )


# ---------------------------------------------------------------------------
# ParamSpecNormalized builder
# ---------------------------------------------------------------------------


def make_param_spec(cfg: ParamSpecConfig | None = None) -> ParamSpecNormalized:
    """Create a ParamSpecNormalized for parameter validation tests."""
    c = cfg or ParamSpecConfig()
    return ParamSpecNormalized(
        name=c.name,
        param_type=c.param_type,
        allow_empty_value=c.allow_empty,
        min_selected_count=c.min_selected,
        max_selected_count=c.max_selected,
        vocabulary=c.vocabulary,
        count_only_leaves=c.count_only_leaves,
        is_number=c.is_number,
        min=c.min,
        max=c.max,
        increment=c.increment,
        max_length=c.max_length,
    )


def add_step_to_graph(graph: StrategyGraph, step: StrategyStep) -> None:
    """Put one step into a graph the way a hydration does.

    Insertion order decides a tie between two roots, so a case adds its steps
    in the order it describes.
    """
    graph.steps[step.id] = step
    graph.recompute_roots()
    graph.last_step_id = step.id
