from __future__ import annotations

from collections.abc import Collection, Iterator, Mapping, Sequence

from veupathdb.domain.parameters import PhyleticNode, PhyleticTree

from pathfinder.domain.strategy.genome_group import MIN_GROUP_GENOMES
from pathfinder.domain.strategy.genome_group_steps import required_genomes
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec

_FEW_CLADES = 3


def _leaves(node: PhyleticNode) -> Iterator[str]:
    if not node.clade:
        yield node.code
    for child in node.children:
        yield from _leaves(child)


def _full(node: PhyleticNode, held: set[str]) -> bool:
    leaves = set(_leaves(node))
    return bool(leaves) and leaves <= held


def _narrowest(node: PhyleticNode) -> PhyleticNode:
    while len(node.children) == 1 and node.children[0].clade:
        node = node.children[0]
    return node


def _cover(nodes: Sequence[PhyleticNode], held: set[str]) -> list[PhyleticNode]:
    found: list[PhyleticNode] = []
    for node in nodes:
        if _full(node, held):
            found.append(_narrowest(node))
        else:
            found.extend(_cover(node.children, held))
    return found


def _spanning(nodes: Sequence[PhyleticNode], held: set[str]) -> list[PhyleticNode]:
    holding = [node for node in nodes if set(_leaves(node)) & held]
    if len(holding) == 1 and holding[0].clade:
        return _spanning(holding[0].children, held)
    return holding


def _share(node: PhyleticNode, held: set[str]) -> str:
    if not node.clade:
        return node.label
    leaves = set(_leaves(node))
    return f"{len(leaves & held):,} of the {len(leaves):,} in {node.label}"


def _joined(names: Sequence[str]) -> str:
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def genome_set_name(tree: PhyleticTree, genomes: Collection[str]) -> str:
    held = set(genomes)
    known = {node.code for node in tree.nodes() if not node.clade}
    unknown = sorted(held - known)
    cover = _cover(tree.roots, held)
    size = f"{len(held):,}"
    if not unknown and len(cover) == 1 and cover[0].clade:
        return f"{size} {cover[0].label} genomes"
    names = [*(node.label for node in cover), *unknown]
    if len(names) <= _FEW_CLADES:
        return f"{size} genomes in {_joined(names)}"
    shares = [*(_share(node, held) for node in _spanning(tree.roots, held)), *unknown]
    return f"{size} genomes ({', '.join(shares)})"


def required_genomes_name(criterion: Criterion, tree: PhyleticTree | None) -> str:
    genomes = required_genomes(criterion)
    if tree is None or len(genomes) < MIN_GROUP_GENOMES:
        return ""
    return genome_set_name(tree, genomes)


def _unnamed(criterion: Criterion) -> bool:
    group = criterion.genome_group
    if group is not None:
        return not group.named
    return (
        not criterion.absence_of
        and not criterion.required_genomes_name
        and len(required_genomes(criterion)) >= MIN_GROUP_GENOMES
    )


def searches_with_unnamed_genomes(spec: OperationalSpec | None) -> set[str]:
    if spec is None:
        return set()
    return {c.search_name for c in spec.criteria if c.search_name and _unnamed(c)}


def _named(criterion: Criterion, tree: PhyleticTree) -> Criterion:
    group = criterion.genome_group
    if group is None:
        return criterion.model_copy(
            update={"required_genomes_name": required_genomes_name(criterion, tree)}
        )
    named = group.named_as(genome_set_name(tree, group.genomes))
    return criterion.model_copy(
        update={"genome_group": named, "text": named.stated_in(criterion.text)}
    )


def _absent_named(criterion: Criterion, lefts: Mapping[str, Criterion]) -> Criterion:
    left = lefts.get(criterion.absence_of)
    group = None if left is None else left.genome_group
    if left is None or group is None:
        return criterion
    return criterion.model_copy(update={"text": group.absent_in(left.unread_text)})


def spec_with_named_genomes(
    spec: OperationalSpec, trees: Mapping[str, PhyleticTree | None]
) -> OperationalSpec:
    named = {
        c.id: _named(c, tree)
        for c in spec.criteria
        if _unnamed(c) and (tree := trees.get(c.search_name)) is not None
    }
    if not named:
        return spec
    criteria = [named.get(c.id, c) for c in spec.criteria]
    lefts = {c.id: c for c in criteria if c.id in named and c.genome_group}
    return spec.model_copy(
        update={"criteria": [_absent_named(c, lefts) for c in criteria]}
    )


__all__ = [
    "genome_set_name",
    "required_genomes_name",
    "searches_with_unnamed_genomes",
    "spec_with_named_genomes",
]
