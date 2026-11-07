from __future__ import annotations

import operator
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from functools import reduce
from typing import Final

from pydantic import Field
from veupathdb.domain.parameters import MultiPickValue, ParamValue, SinglePickValue
from veupathdb.domain.strategy import CombineOp
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    CriterionRole,
    OperationalSpec,
    StructureNode,
)
from pathfinder.domain.strategy.step_naming import cut_on_a_word


class OfferedReading(CamelModel):
    label: str
    plan: str
    gene_count: int | None
    spec: OperationalSpec
    not_counted: str = ""
    also: str = Field(default="")


_BUILD_MESSAGE: Final = re.compile(r'Build "(?P<label>.+)"\.')


def build_message(label: str) -> str:
    return f'Build "{label}".'


def label_built_by(message: str) -> str | None:
    found = _BUILD_MESSAGE.fullmatch(message.strip())
    return None if found is None else found["label"]


def _picked(value: ParamValue) -> list[str]:
    match value:
        case MultiPickValue(values=values):
            return list(values)
        case SinglePickValue(value=picked):
            return [picked]
        case _:
            return []


def plan_organisms(spec: OperationalSpec) -> list[str]:
    return [
        organism
        for criterion in spec.criteria
        if criterion.organism_param is not None
        and (bound := criterion.resolved_params.get(criterion.organism_param))
        is not None
        for organism in _picked(bound.value)
    ]


def picked_plan_text(offered: OfferedReading) -> str:
    lines = [
        (
            "The researcher picked this plan, which Explore proposed. Frame it as "
            "stated, and change it only where a requirement or the site disagrees:"
        ),
        *plan_lines(offered.spec),
    ]
    if offered.also:
        lines.append(f"Explore also suggested: {offered.also}")
    return "\n".join(lines)


type _SetOp = Callable[[frozenset[str], frozenset[str]], frozenset[str]]

_COUNTED: Final[dict[CombineOp, _SetOp]] = {
    CombineOp.INTERSECT: operator.and_,
    CombineOp.UNION: operator.or_,
    CombineOp.MINUS: operator.sub,
}
_KINDS: Final = frozenset({"leaf", "combine"})
_RIGHT_ROLES: Final[dict[CombineOp, CriterionRole]] = {
    CombineOp.INTERSECT: "filter",
    CombineOp.MINUS: "exclude",
}


def _leaves(node: StructureNode) -> Iterator[str]:
    if node.kind == "leaf":
        yield node.named_criterion
    for child in node.inputs:
        yield from _leaves(child)


def _nodes(node: StructureNode) -> Iterator[StructureNode]:
    yield node
    for child in node.inputs:
        yield from _nodes(child)


def reading_shape_refusal(root: StructureNode, names: Sequence[str]) -> str | None:
    for node in _nodes(root):
        if node.kind not in _KINDS:
            return (
                f"A reading states searches and combines, not a {node.kind}. "
                "Build states a transform or a copy."
            )
        if node.kind == "combine" and node.combine_operator not in _COUNTED:
            return (
                "A reading combines searches with INTERSECT, UNION or MINUS, "
                f"not {node.combine_operator.value}."
            )
    stated = list(_leaves(root))
    unknown = [name for name in stated if name not in names]
    if unknown:
        return (
            f"The structure names {', '.join(unknown)}, which is no search of this "
            f"reading. Its searches are: {', '.join(names)}."
        )
    missing = [name for name in names if name not in stated]
    if missing:
        return (
            f"The structure leaves out {', '.join(missing)}. Every search of a "
            "reading is in its structure."
        )
    return None


def combined_ids(
    node: StructureNode, ids: Mapping[str, frozenset[str]]
) -> frozenset[str]:
    if node.kind == "leaf":
        return ids[node.named_criterion]
    held = [combined_ids(child, ids) for child in node.inputs]
    return reduce(_COUNTED[node.combine_operator], held)


def reading_roles(
    node: StructureNode, role: CriterionRole = "seed"
) -> dict[str, CriterionRole]:
    if node.kind == "leaf":
        return {node.named_criterion: role}
    first, *rest = node.inputs
    rest_role = _RIGHT_ROLES.get(node.combine_operator, role)
    roles = reading_roles(first, role)
    for child in rest:
        roles |= reading_roles(child, rest_role)
    return roles


def _named(criterion: Criterion) -> str:
    head = criterion.search_display_name or criterion.search_name
    shown = ", ".join(
        bound.label or bound.value.to_wire()
        for name, bound in criterion.resolved_params.items()
        if bound.visible and name != criterion.organism_param
    )
    title = f"{head}: {cut_on_a_word(shown)}" if shown else head
    organism = (
        criterion.resolved_params.get(criterion.organism_param)
        if criterion.organism_param is not None
        else None
    )
    if organism is None or not organism.label:
        return title
    return f"{title} ({organism.label})"


def _worded(node: StructureNode, names: Mapping[str, str], *, top: bool) -> str:
    if node.kind == "leaf":
        return names[node.named_criterion]
    joined = f" {node.combine_operator.value} ".join(
        _worded(child, names, top=False) for child in node.inputs
    )
    return joined if top else f"({joined})"


def _ids(node: StructureNode) -> dict[str, str]:
    return {name: name for name in _leaves(node)}


def plan_lines(spec: OperationalSpec) -> list[str]:
    if spec.structure is None:
        msg = "A reading's spec states its structure."
        raise ValueError(msg)
    searches = [
        f"- {c.id}: {c.search_name} ({c.search_display_name}), "
        + ", ".join(
            f"{name}={bound.value.to_wire()}"
            for name, bound in c.resolved_params.items()
        )
        for c in spec.criteria
    ]
    root = spec.structure.root
    return [*searches, f"- structure: {_worded(root, _ids(root), top=True)}"]


def reading_label(spec: OperationalSpec) -> str:
    names = {criterion.id: _named(criterion) for criterion in spec.criteria}
    if spec.structure is None:
        msg = "A reading's spec states its structure."
        raise ValueError(msg)
    return _worded(spec.structure.root, names, top=True)


__all__ = [
    "OfferedReading",
    "build_message",
    "combined_ids",
    "label_built_by",
    "picked_plan_text",
    "plan_lines",
    "plan_organisms",
    "reading_label",
    "reading_roles",
    "reading_shape_refusal",
]
