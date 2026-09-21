"""What a test reads back after a turn: the live steps and the committed ops.

Both are stated in wire form, so an assertion names the value VEuPathDB is
sent rather than the Python object that carries it.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field
from veupathdb.domain.parameters import ParamValue, to_wire
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.operations import (
    AddCombineOp,
    AddLeafOp,
    AddTransformOp,
    DeleteStepOp,
    GraphOperation,
    ReplaceSubtreeOp,
    UpdateCombineOperatorOp,
    UpdateStepMetaOp,
    UpdateStepParamsOp,
    WireInputOp,
)
from pathfinder.domain.strategy.session import StrategyGraph


def wire(params: dict[str, ParamValue]) -> dict[str, str]:
    return {name: to_wire(value) for name, value in params.items()}


class StepFacts(CamelModel):
    """One live step, in the form two turns are compared by."""

    model_config = ConfigDict(frozen=True)

    search_name: str | None = None
    operator: str | None = None
    primary_input_id: str | None = None
    secondary_input_id: str | None = None
    parameters: dict[str, str] = Field(default_factory=dict)


def step_facts(graph: StrategyGraph, step_id: str) -> StepFacts:
    step = graph.steps[step_id]
    return StepFacts(
        search_name=step.search_name,
        operator=None if step.operator is None else step.operator.value,
        primary_input_id=step.primary_input_id,
        secondary_input_id=step.secondary_input_id,
        parameters=wire(step.parameters),
    )


def graph_facts(graph: StrategyGraph) -> dict[str, StepFacts]:
    """Every live step by id, so an unnamed step's survival is one equality."""
    return {step_id: step_facts(graph, step_id) for step_id in graph.steps}


def facts_of(facts: dict[str, StepFacts], *step_ids: str) -> dict[str, StepFacts]:
    """The subset a test states, which is every step the request left alone."""
    return {step_id: facts[step_id] for step_id in step_ids if step_id in facts}


class OpFacts(CamelModel):
    """One committed operation: its kind, the step it addresses, its payload."""

    model_config = ConfigDict(frozen=True)

    kind: str
    step_id: str
    parameters: dict[str, str] = Field(default_factory=dict)
    search_name: str | None = None
    operator: str | None = None
    left_id: str | None = None
    right_id: str | None = None
    input_id: str | None = None
    slot: str | None = None
    resolution: str | None = None


def _added_facts(op: GraphOperation) -> OpFacts | None:
    """The three operations that put a new step on the strategy."""
    match op:
        case AddLeafOp():
            return OpFacts(
                kind=op.kind,
                step_id=op.step.id,
                parameters=wire(op.step.parameters),
                search_name=op.step.search_name,
                slot=op.attach.mode,
            )
        case AddCombineOp():
            return OpFacts(
                kind=op.kind,
                step_id=op.step.id,
                operator=None if op.step.operator is None else op.step.operator.value,
                left_id=op.left_id,
                right_id=op.right_id,
            )
        case AddTransformOp():
            return OpFacts(
                kind=op.kind,
                step_id=op.step.id,
                parameters=wire(op.step.parameters),
                search_name=op.step.search_name,
                input_id=op.input_id,
                slot=op.mode,
            )
        case _:
            return None


def _updated_facts(op: GraphOperation) -> OpFacts | None:
    """The three operations that write one field of a step that already exists."""
    match op:
        case UpdateStepParamsOp():
            return OpFacts(
                kind=op.kind, step_id=op.step_id, parameters=wire(op.parameters)
            )
        case UpdateCombineOperatorOp():
            return OpFacts(kind=op.kind, step_id=op.step_id, operator=op.operator.value)
        case UpdateStepMetaOp():
            return OpFacts(
                kind=op.kind, step_id=op.step_id, search_name=op.display_name
            )
        case _:
            return None


def _rewired_facts(op: GraphOperation) -> OpFacts | None:
    """The operations that move or remove a whole branch."""
    match op:
        case DeleteStepOp():
            return OpFacts(
                kind=op.kind, step_id=op.step_id, resolution=op.resolution.value
            )
        case WireInputOp():
            return OpFacts(
                kind=op.kind,
                step_id=op.target_step_id,
                input_id=op.source_step_id,
                slot=op.slot,
            )
        case ReplaceSubtreeOp():
            return OpFacts(
                kind=op.kind,
                step_id=op.step_id,
                parameters=wire(op.subtree.parameters),
                search_name=op.subtree.search_name,
                operator=(
                    None if op.subtree.operator is None else op.subtree.operator.value
                ),
                left_id=op.subtree.primary_input_id,
                right_id=op.subtree.secondary_input_id,
            )
        case _:
            return None


def op_facts(op: GraphOperation) -> OpFacts:
    """The whole of one operation, flattened for an exact comparison."""
    found = _added_facts(op) or _updated_facts(op) or _rewired_facts(op)
    return found if found is not None else OpFacts(kind=op.kind, step_id="")


def committed_facts(ops: list[GraphOperation]) -> list[OpFacts]:
    return [op_facts(op) for op in ops]


def spec_facts(spec: OperationalSpec) -> dict[str, dict[str, str]]:
    """Every criterion's bound values, keyed by criterion id."""
    return {c.id: wire(c.resolved_params) for c in spec.criteria}
