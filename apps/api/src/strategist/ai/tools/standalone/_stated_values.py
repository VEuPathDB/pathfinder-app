"""The values a model states for a search, read by each parameter's rule."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Annotated, Literal, Self

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Discriminator, Field, JsonValue, ValidationError, model_validator
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    ColocationParams,
    CombineOp,
    StrategyStepNode,
    generate_step_id,
)
from veupathdb.errors import VEuPathDBError
from veupathdb_mcp.catalog import read_stated_parameters

from strategist.domain.strategy.operations import (
    AddCombineOp,
    AddLeafOp,
    AddTransformOp,
    DuplicateStepOp,
    EditableOperation,
    UpdateCombineOperatorOp,
    UpdateStepMetaOp,
    UpdateStepParamsOp,
    UpdateStrategyMetaOp,
    WireInputOp,
)
from strategist.domain.strategy.operations.types import AttachPoint
from strategist.domain.strategy.session import StrategyGraph

_NOTHING_BOUND: Mapping[str, ParamValue] = MappingProxyType({})


async def typed_values(
    site_id: str,
    search_name: str,
    stated: Mapping[str, JsonValue],
    *,
    record_type: str | None = None,
    bound: Mapping[str, ParamValue] = _NOTHING_BOUND,
) -> dict[str, ParamValue]:
    try:
        return await read_stated_parameters(
            site_id, search_name, stated, record_type=record_type, bound=bound
        )
    except VEuPathDBError as exc:
        msg = f"{search_name}: {exc.detail or exc.title} Nothing was written."
        raise ModelRetry(msg) from exc


class StatedStepNode(CamelModel):
    search_name: str | None = None
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    primary_input: StatedStepNode | None = None
    secondary_input: StatedStepNode | None = None
    operator: CombineOp | None = None
    colocation_params: ColocationParams | None = None
    display_name: str | None = None
    wdk_weight: int | None = None
    id: str = Field(default_factory=generate_step_id)

    @model_validator(mode="after")
    def _named(self) -> Self:
        if self.search_name is None and self.secondary_input is None:
            msg = "searchName is required on a search and on a transform"
            raise ValueError(msg)
        return self

    def search_names(self) -> list[str]:
        inputs = (self.primary_input, self.secondary_input)
        below = [name for node in inputs if node for name in node.search_names()]
        return [*below, *([self.search_name] if self.search_name else [])]


async def typed_tree(site_id: str, node: StatedStepNode) -> StrategyStepNode:
    primary, secondary = [
        None if child is None else await typed_tree(site_id, child)
        for child in (node.primary_input, node.secondary_input)
    ]
    search_name = node.search_name or COMBINE_SEARCH_NAME
    parameters = await typed_values(site_id, search_name, node.parameters)
    try:
        return StrategyStepNode(
            id=node.id,
            search_name=search_name,
            parameters=parameters,
            primary_input=primary,
            secondary_input=secondary,
            operator=node.operator,
            colocation_params=node.colocation_params,
            display_name=node.display_name,
            wdk_weight=node.wdk_weight,
        )
    except ValidationError as exc:
        raise ModelRetry(str(exc)) from exc


class StatedAddLeafOp(CamelModel):
    kind: Literal["addLeaf"] = "addLeaf"
    step: StatedStepNode
    attach: AttachPoint


class StatedAddCombineOp(CamelModel):
    kind: Literal["addCombine"] = "addCombine"
    step: StatedStepNode
    left_id: str
    right_id: str


class StatedAddTransformOp(CamelModel):
    kind: Literal["addTransform"] = "addTransform"
    step: StatedStepNode
    input_id: str
    mode: Literal["before-consumer", "new-root"]


class StatedUpdateStepParamsOp(CamelModel):
    kind: Literal["updateStepParams"] = "updateStepParams"
    step_id: str
    parameters: dict[str, JsonValue]


StatedOperation = Annotated[
    StatedAddLeafOp
    | StatedAddCombineOp
    | StatedAddTransformOp
    | StatedUpdateStepParamsOp
    | DuplicateStepOp
    | UpdateCombineOperatorOp
    | UpdateStepMetaOp
    | UpdateStrategyMetaOp
    | WireInputOp,
    Discriminator("kind"),
]


async def typed_operation(
    site_id: str,
    op: StatedOperation,
    searches: Mapping[str, str],
    held: Mapping[str, Mapping[str, ParamValue]],
) -> EditableOperation:
    match op:
        case StatedAddLeafOp(step=step, attach=attach):
            return AddLeafOp(step=await typed_tree(site_id, step), attach=attach)
        case StatedAddCombineOp(step=step, left_id=left_id, right_id=right_id):
            tree = await typed_tree(site_id, step)
            return AddCombineOp(step=tree, left_id=left_id, right_id=right_id)
        case StatedAddTransformOp(step=step, input_id=input_id, mode=mode):
            tree = await typed_tree(site_id, step)
            return AddTransformOp(step=tree, input_id=input_id, mode=mode)
        case StatedUpdateStepParamsOp(step_id=step_id, parameters=stated):
            if step_id not in searches:
                msg = f"No step {step_id!r} runs a search. Steps: {sorted(searches)}."
                raise ModelRetry(msg)
            values = await typed_values(
                site_id, searches[step_id], stated, bound=held.get(step_id, {})
            )
            return UpdateStepParamsOp(step_id=step_id, parameters=values)
        case _:
            return op


async def typed_operations(
    site_id: str, graph: StrategyGraph, ops: Sequence[StatedOperation]
) -> list[EditableOperation]:
    searches = {
        step_id: step.search_name
        for step_id, step in graph.steps.items()
        if step.search_name
    }
    held = {step_id: step.parameters for step_id, step in graph.steps.items()}
    typed: list[EditableOperation] = []
    for op in ops:
        read = await typed_operation(site_id, op, searches, held)
        match read:
            case AddLeafOp(step=step) | AddTransformOp(step=step):
                searches[step.id] = step.search_name
                held[step.id] = step.parameters
            case UpdateStepParamsOp(step_id=step_id, parameters=parameters):
                held[step_id] = {**held.get(step_id, {}), **parameters}
            case _:
                pass
        typed.append(read)
    return typed
