from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import count

from veupathdb.domain.parameters import (
    ParamValue,
    PhyleticBinding,
    PhyleticNode,
    PhyleticTree,
    StringValue,
    TriState,
    derive_binding,
    read_census,
    to_wire,
)
from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.genome_group import PROFILE_PATTERN, GenomeGroup
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    structure_criteria,
)
from pathfinder.domain.strategy.spec_reconciliation import spec_without_steps

_STRAIN_KINDS = frozenset({"any_strain", "all_strains"})


def _census_tree(codes: Sequence[str]) -> PhyleticTree:
    return PhyleticTree(
        roots=[
            PhyleticNode(code=code, label=code, depth=1, clade=False)
            for code in sorted(codes)
        ]
    )


def _binding_of(states: Mapping[str, TriState]) -> PhyleticBinding:
    included = sorted(code for code, state in states.items() if state == "include")
    excluded = sorted(code for code, state in states.items() if state == "exclude")
    match derive_binding(_census_tree(list(states)), included, excluded):
        case PhyleticBinding() as binding:
            return binding
        case refused:
            raise ValueError(refused)


def _census(criterion: Criterion) -> dict[str, TriState] | None:
    held = criterion.resolved_params.get(PROFILE_PATTERN)
    return None if held is None else read_census(to_wire(held.value)).states


def required_genomes(criterion: Criterion) -> list[str]:
    states = _census(criterion) or {}
    return sorted(code for code, state in states.items() if state == "include")


def _group_at_least_one(criterion: Criterion) -> GenomeGroup | None:
    group = criterion.genome_group
    return group if group is not None and group.at_least_one else None


def _with_binding(
    params: Mapping[str, BoundValue], binding: PhyleticBinding
) -> dict[str, BoundValue]:
    derived: dict[str, ParamValue] = {
        name: StringValue(value=wire) for name, wire in binding.model_dump().items()
    }
    return {
        name: bound.model_copy(update={"value": derived.get(name, bound.value)})
        for name, bound in params.items()
    }


def _wire_of(criterion: Criterion) -> dict[str, str]:
    return {name: to_wire(value) for name, value in criterion.param_values.items()}


def _left_of(criterion: Criterion, group: GenomeGroup) -> Criterion:
    states = _census(criterion) or {}
    kept: dict[str, TriState] = {
        code: state for code, state in states.items() if code not in group.genomes
    }
    params = _with_binding(criterion.resolved_params, _binding_of(kept))
    left = criterion.model_copy(update={"resolved_params": params})
    if _wire_of(left) == _wire_of(criterion):
        return criterion
    return left.model_copy(update={"result_count": None})


def _right_of(left: Criterion, group: GenomeGroup, right_id: str) -> Criterion:
    absent: dict[str, TriState] = {**(_census(left) or {})}
    absent.update((genome, "exclude") for genome in group.genomes)
    held = {
        name: bound.sourced("held").model_copy(update={"label": ""})
        for name, bound in left.resolved_params.items()
    }
    return left.model_copy(
        update={
            "id": right_id,
            "text": f"{left.text} (none of {len(group.genomes)} genomes)",
            "role": "exclude",
            "answers": [],
            "absence_of": left.id,
            "genome_group": None,
            "measurements": [],
            "alternatives": [],
            "open_params": [],
            "rationale": None,
            "accepted_reading": None,
            "result_count": None,
            "resolved_params": _with_binding(held, _binding_of(absent)),
        }
    )


def _rights_held(spec: OperationalSpec) -> dict[str, Criterion]:
    return {c.absence_of: c for c in spec.criteria if c.absence_of}


def _derived_right(
    left: Criterion, group: GenomeGroup, kept: Criterion | None, taken: set[str]
) -> Criterion:
    right_id = kept.id if kept is not None else _free_id(left.id, taken)
    right = _right_of(left, group, right_id)
    if kept is not None and _wire_of(kept) == _wire_of(right):
        return right.model_copy(update={"result_count": kept.result_count})
    return right


def _free_id(left_id: str, taken: set[str]) -> str:
    first = f"{left_id}_absent"
    if first not in taken:
        return first
    return next(
        candidate
        for candidate in (f"{first}_{n}" for n in count(2))
        if candidate not in taken
    )


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _with_minus(node: StructureNode, rights: Mapping[str, str]) -> StructureNode:
    if node.kind == "leaf" and node.named_criterion in rights:
        return StructureNode(
            kind="combine",
            operator=CombineOp.MINUS,
            inputs=[node, _leaf(rights[node.named_criterion])],
        )
    inputs = [_with_minus(child, rights) for child in node.inputs]
    return node.model_copy(update={"inputs": inputs})


def spec_with_group_steps(spec: OperationalSpec) -> OperationalSpec:
    if spec.structure is None or not any(
        c.absence_of or _group_at_least_one(c) for c in spec.criteria
    ):
        return spec
    named = structure_criteria(spec.structure)
    waiting = {c.id for c in spec.criteria if c.open_params}
    held = _rights_held(spec)
    pruned = spec_without_steps(
        spec,
        [right.id for left_id, right in held.items() if left_id not in waiting],
    )
    if pruned.structure is None:
        return pruned
    taken = {c.id for c in spec.criteria}
    criteria: list[Criterion] = []
    minus: dict[str, str] = {}
    for criterion in pruned.criteria:
        group = _group_at_least_one(criterion)
        if (
            group is None
            or criterion.id not in named
            or not criterion.bound
            or criterion.id in waiting
            or _census(criterion) is None
        ):
            criteria.append(criterion)
            continue
        left = _left_of(criterion, group)
        right = _derived_right(left, group, held.get(left.id), taken)
        taken.add(right.id)
        minus[left.id] = right.id
        criteria.extend([left, right])
    return pruned.model_copy(
        update={
            "criteria": criteria,
            "structure": SpecStructure(root=_with_minus(pruned.structure.root, minus)),
        }
    )


def spec_read_on_genomes(
    spec: OperationalSpec, criterion_id: str, group: GenomeGroup
) -> OperationalSpec:
    settled = [
        c.model_copy(update={"genome_group": group}) if c.id == criterion_id else c
        for c in spec.criteria
    ]
    return spec_with_group_steps(spec.model_copy(update={"criteria": settled}))


def _holds_every_genome(criterion: Criterion, group: GenomeGroup) -> bool:
    return set(group.genomes) <= set(required_genomes(criterion))


def criterion_keeping_its_reading(held: Criterion, bound: Criterion) -> Criterion:
    group = held.genome_group
    if (
        group is None
        or bound.search_name != held.search_name
        or not (_holds_every_genome(bound, group) or _wire_of(bound) == _wire_of(held))
    ):
        return bound
    return bound.model_copy(update={"genome_group": group})


def _subtracted(node: StructureNode, left_id: str, right_id: str) -> bool:
    if (
        node.kind == "combine"
        and node.operator is CombineOp.MINUS
        and _leaf(left_id) == node.inputs[0]
        and _leaf(right_id) in node.inputs[1:]
    ):
        return True
    return any(_subtracted(child, left_id, right_id) for child in node.inputs)


def _reading_stands(
    left: Criterion, group: GenomeGroup, right: Criterion | None, spec: OperationalSpec
) -> bool:
    states = _census(left)
    if states is None:
        return False
    if not group.at_least_one or right is None:
        return _holds_every_genome(left, group)
    return (
        spec.structure is not None
        and _subtracted(spec.structure.root, left.id, right.id)
        and not set(group.genomes) & set(states)
        and right.search_name == left.search_name
        and _wire_of(right) == _wire_of(_right_of(left, group, right.id))
    )


def _criterion_kept(criterion: Criterion, standing: set[str]) -> Criterion:
    if criterion.absence_of and criterion.absence_of not in standing:
        return criterion.model_copy(update={"absence_of": ""})
    if criterion.genome_group is None or criterion.id in standing:
        return criterion
    return criterion.model_copy(
        update={
            "genome_group": None,
            "measurements": [
                m for m in criterion.measurements if m.kind not in _STRAIN_KINDS
            ],
        }
    )


def spec_with_unstated_groups_retired(spec: OperationalSpec) -> OperationalSpec:
    if not any(c.absence_of or c.genome_group for c in spec.criteria):
        return spec
    held = _rights_held(spec)
    standing = {
        c.id
        for c in spec.criteria
        if c.genome_group is not None
        and _reading_stands(c, c.genome_group, held.get(c.id), spec)
    }
    criteria = [_criterion_kept(c, standing) for c in spec.criteria]
    return spec.model_copy(update={"criteria": criteria})
