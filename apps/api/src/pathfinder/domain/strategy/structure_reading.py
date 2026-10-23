from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain.strategy import StepKind, StrategyStep, record_class_of

NODE_SHAPES = {
    "leaf": (
        'a leaf is {"kind": "leaf", "criterionId": "<id>"}: one bound criterion, '
        "with no inputs and no operator."
    ),
    "combine": (
        'a combine is {"kind": "combine", "operator": "INTERSECT" | "UNION" | '
        '"MINUS", "inputs": [<left>, <right>]}: an operator over two or more '
        "subtrees, with no criterionId. A tree of one criterion is that "
        "criterion's leaf; with no criterion left, there is no tree to set."
    ),
    "transform": (
        'a transform is {"kind": "transform", "criterionId": "<id>", "inputs": '
        "[<subtree>]}: one criterion that maps exactly one input subtree, with no "
        "operator."
    ),
    "copy": (
        'a copy is {"kind": "copy", "inputs": [<subtree>]}: exactly one subtree '
        "the tree already states, with no criterionId and no operator."
    ),
}


class SpareWrapper(BaseModel):
    """A raw combine node of exactly one input."""

    model_config = ConfigDict(extra="ignore", from_attributes=True)

    kind: Literal["combine"]
    inputs: Annotated[list[object], Field(min_length=1, max_length=1)]


class StatedNode(Protocol):
    @property
    def criterion_id(self) -> str | None: ...

    @property
    def inputs(self) -> Sequence[StatedNode]: ...


def record_class_at(
    roots: Sequence[StatedNode], classes: Mapping[str, str | None]
) -> str | None:
    steps: dict[str, StrategyStep] = {}
    _add_joined(roots, "root", classes, steps)
    return record_class_of("root", steps)


def _add_joined(
    nodes: Sequence[StatedNode],
    at: str,
    classes: Mapping[str, str | None],
    steps: dict[str, StrategyStep],
) -> None:
    if len(nodes) != 1:
        _add_step(at, None, nodes, classes, steps)
    elif nodes[0].criterion_id:
        _add_step(at, classes.get(nodes[0].criterion_id), (), classes, steps)
    else:
        _add_step(at, None, nodes[0].inputs, classes, steps)


def _add_step(
    at: str,
    own: str | None,
    inputs: Sequence[StatedNode],
    classes: Mapping[str, str | None],
    steps: dict[str, StrategyStep],
) -> None:
    steps[at] = StrategyStep(
        id=at,
        kind=StepKind.COMBINE,
        record_class=own,
        primary_input_id=f"{at}.0" if inputs else None,
        secondary_input_id=f"{at}.1" if len(inputs) > 1 else None,
    )
    if inputs:
        _add_joined(inputs[:1], f"{at}.0", classes, steps)
    if len(inputs) > 1:
        _add_joined(inputs[1:], f"{at}.1", classes, steps)
