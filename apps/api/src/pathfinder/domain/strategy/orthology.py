"""The orthology round trip, the copy of a subtree it reads, and the organism a
tree's records belong to."""

from __future__ import annotations

import json
from collections.abc import Collection, Iterator, Mapping

from pydantic import ConfigDict
from veupathdb.domain.parameters import (
    MultiPickValue,
    SinglePickValue,
    StringValue,
    to_wire,
)
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    extract_output_organisms,
    generate_step_id,
)
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)

__all__ = [
    "OrganismChange",
    "copy_refusal",
    "organism_change",
    "restate_copies",
    "round_trip_refusal",
    "stated_steps",
]

_KEPT_BY_INTERSECT = (
    '{"kind": "combine", "operator": "INTERSECT", "inputs": [<the source subtree>, '
    "<the transform back>]}"
)
_COPY = '{"kind": "copy", "inputs": [<the source subtree>]}'


class OrganismChange(CamelModel):
    """The organisms the seed searched and the ones the records now belong to."""

    model_config = ConfigDict(frozen=True)

    seed: list[str]
    records: list[str]

    def line(self) -> str:
        return f"{', '.join(self.records)} (the seed searched {', '.join(self.seed)})"


def organism_change(root: StrategyStepNode) -> OrganismChange | None:
    """How the root's organisms differ from the seed's, or None when they agree.

    The seed is the deepest primary leaf. Either side unknown is no change.
    """
    seed = root
    while seed.primary_input is not None:
        seed = seed.primary_input
    searched = extract_output_organisms(seed)
    answered = extract_output_organisms(root)
    if not searched or not answered or searched == answered:
        return None
    return OrganismChange(seed=sorted(searched), records=sorted(answered))


def restate_copies(spec: OperationalSpec) -> OperationalSpec:
    """The spec with each copy node stated as criteria of its own.

    A copy of a subtree whose criteria are not all bound stays a copy, so it
    follows the criteria it restates until they bind.
    """
    if spec.structure is None or not _holds_a_copy(spec.structure.root):
        return spec
    by_id = {c.id: c for c in spec.criteria}
    clones: list[Criterion] = []
    root = _restated(spec.structure.root, by_id, clones)
    if not clones:
        return spec
    return spec.model_copy(
        update={
            "criteria": [*spec.criteria, *clones],
            "structure": SpecStructure(root=root),
        }
    )


def _holds_a_copy(node: StructureNode) -> bool:
    return node.kind == "copy" or any(_holds_a_copy(child) for child in node.inputs)


def _restated(
    node: StructureNode, by_id: dict[str, Criterion], clones: list[Criterion]
) -> StructureNode:
    inputs = [_restated(child, by_id, clones) for child in node.inputs]
    if node.kind != "copy" or len(inputs) != 1:
        return node.model_copy(update={"inputs": inputs})
    source = inputs[0]
    copied = [by_id.get(cid) for cid in _criteria_of(source)]
    if not all(c is not None and c.bound and not c.open_params for c in copied):
        return node.model_copy(update={"inputs": inputs})
    fresh = {cid: generate_step_id() for cid in _criteria_of(source)}
    for cid, new_id in fresh.items():
        clone = by_id[cid].model_copy(
            deep=True, update={"id": new_id, "rationale": None}
        )
        by_id[new_id] = clone
        clones.append(clone)
    return _renamed(source, fresh)


def _criteria_of(node: StructureNode) -> list[str]:
    own = [node.criterion_id] if node.kind != "combine" and node.criterion_id else []
    return [*own, *(cid for child in node.inputs for cid in _criteria_of(child))]


def _renamed(node: StructureNode, fresh: Mapping[str, str]) -> StructureNode:
    return node.model_copy(
        update={
            "criterion_id": fresh.get(node.criterion_id or "", node.criterion_id),
            "inputs": [_renamed(child, fresh) for child in node.inputs],
        }
    )


def copy_refusal(root: StructureNode) -> str | None:
    """Why the tree's copies or repeated criteria are refused, or None.

    A criterion id appears once outside the copies, and a copy restates a
    subtree the tree states outside a copy, node for node.
    """
    stated = list(_outside_copies(root))
    seen: set[str] = set()
    for node in stated:
        cid = node.criterion_id
        if node.kind != "combine" and cid:
            if cid in seen:
                return (
                    f"{cid} appears twice in the tree. A subtree the tree already "
                    f'states is stated again as {{"kind": "copy", "inputs": '
                    f"[<that subtree>]}}, and the build gives the copy steps of "
                    f"its own."
                )
            seen.add(cid)
    for copy in _copies(root):
        if len(copy.inputs) != 1:
            return f"A copy takes one input, the subtree it restates; {_COPY}."
        if copy.inputs[0] not in stated:
            return (
                "A copy restates a subtree the tree states outside a copy, node "
                "for node: the same kinds, criteria and operators. Copy that "
                "subtree as it stands."
            )
    return None


def _outside_copies(node: StructureNode) -> Iterator[StructureNode]:
    if node.kind == "copy":
        return
    yield node
    for child in node.inputs:
        yield from _outside_copies(child)


def _copies(node: StructureNode) -> Iterator[StructureNode]:
    if node.kind == "copy":
        yield node
    for child in node.inputs:
        yield from _copies(child)


def round_trip_refusal(
    spec: OperationalSpec, *, touched: Collection[str] | None = None
) -> str | None:
    """Why a round trip of the spec's tree is refused, or None.

    ``touched`` limits the reading to the round trips whose legs it names; None
    reads every one.
    """
    tree = stated_steps(spec)
    if tree is None:
        return None
    by_id = {c.id: c for c in spec.criteria}
    for back, parent in _with_parents(tree, None):
        there = back.primary_input
        if not _is_transform(back) or there is None or not _is_transform(there):
            continue
        if touched is not None and not {back.id, there.id} & set(touched):
            continue
        refusal = _refused_trip(back, there, parent, by_id)
        if refusal is not None:
            return refusal
    return None


def _refused_trip(
    back: StrategyStepNode,
    there: StrategyStepNode,
    parent: StrategyStepNode | None,
    by_id: Mapping[str, Criterion],
) -> str | None:
    source = there.primary_input
    if source is None:
        return None
    organisms = extract_output_organisms(source)
    mapped = extract_output_organisms(there)
    if not organisms or organisms != extract_output_organisms(back):
        return None
    if mapped == organisms:
        return None
    unequal = _unequal_legs(there, back, mapped or set(), organisms)
    if unequal is not None:
        return unequal
    if parent is not None and parent.operator is CombineOp.INTERSECT:
        other = (
            parent.secondary_input
            if parent.primary_input is back
            else parent.primary_input
        )
        if other is not None and _shape(other) == _shape(source):
            return None
    name = _named(back.id, by_id)
    return (
        f"{name} maps the genes of {there.id} back to {', '.join(sorted(organisms))}. "
        f"A round trip alone returns every source gene that is an ortholog or a "
        f"paralog of a mapped gene, which holds genes the source never held. Keep "
        f"the source genes: state {_KEPT_BY_INTERSECT}, and give the first "
        f"transform {_COPY} as its input."
    )


def _unequal_legs(
    there: StrategyStepNode,
    back: StrategyStepNode,
    mapped: set[str],
    organisms: set[str],
) -> str | None:
    """Why the two legs of one round trip differ past the organism each maps to.

    A value that names the leg's own organisms is where the legs differ; every
    other value the two legs share asks the same question both ways.
    """
    for name in sorted(set(there.parameters) & set(back.parameters)):
        values = [_wire(there, name), _wire(back, name)]
        if values[0] == values[1]:
            continue
        if _names(there, name, mapped) and _names(back, name, organisms):
            continue
        return (
            f"{there.id} and {back.id} are the two legs of one round trip, and "
            f"{name} differs: {values[0]} and {values[1]}. Both legs carry the "
            f"same values, except the organism each maps to."
        )
    return None


def _names(node: StrategyStepNode, name: str, organisms: set[str]) -> bool:
    """Whether the parameter's value is exactly these organisms."""
    match node.parameters.get(name):
        case MultiPickValue(values=values):
            return set(values) == organisms
        case SinglePickValue(value=value) | StringValue(value=value):
            return {value} == organisms
        case _:
            return False


def _wire(node: StrategyStepNode, name: str) -> str:
    value = node.parameters.get(name)
    return "" if value is None else to_wire(value)


def _named(criterion_id: str, by_id: Mapping[str, Criterion]) -> str:
    criterion = by_id.get(criterion_id)
    title = criterion.search_display_name if criterion is not None else None
    return criterion_id if not title else f"{criterion_id} ({title})"


def _is_transform(node: StrategyStepNode) -> bool:
    return node.primary_input is not None and node.secondary_input is None


def _with_parents(
    node: StrategyStepNode, parent: StrategyStepNode | None
) -> Iterator[tuple[StrategyStepNode, StrategyStepNode | None]]:
    yield node, parent
    for child in node.inputs():
        yield from _with_parents(child, node)


def _shape(node: StrategyStepNode) -> str:
    """The node's searches, values and operators, without its ids."""
    return json.dumps(
        [
            node.search_name,
            None if node.operator is None else node.operator.value,
            sorted((name, to_wire(value)) for name, value in node.parameters.items()),
            [_shape(child) for child in node.inputs()],
        ]
    )


def stated_steps(spec: OperationalSpec) -> StrategyStepNode | None:
    """The spec's stated tree as steps keyed on their criteria, bound or not."""
    if spec.structure is None:
        return None
    return _projected(spec.structure.root, {c.id: c for c in spec.criteria})


def _projected(node: StructureNode, by_id: Mapping[str, Criterion]) -> StrategyStepNode:
    """The stated tree as steps, each keyed on its criterion, bound or not."""
    if node.kind == "combine" and len(node.inputs) != 1:
        steps = [_projected(child, by_id) for child in node.inputs]
        joined = steps[0] if steps else StrategyStepNode(search_name="")
        for step in steps[1:]:
            joined = StrategyStepNode(
                search_name=COMBINE_SEARCH_NAME,
                operator=node.operator or CombineOp.INTERSECT,
                primary_input=joined,
                secondary_input=step,
            )
        return joined
    if node.kind in ("combine", "copy"):
        return (
            _projected(node.inputs[0], by_id)
            if node.inputs
            else StrategyStepNode(search_name="")
        )
    criterion = by_id.get(node.criterion_id or "")
    return StrategyStepNode(
        id=node.criterion_id or generate_step_id(),
        search_name=criterion.search_name if criterion is not None else "",
        parameters=dict(criterion.resolved_params) if criterion is not None else {},
        primary_input=(
            _projected(node.inputs[0], by_id)
            if node.kind == "transform" and node.inputs
            else None
        ),
    )
