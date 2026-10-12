"""The edit a refused INTERSECT of two organism scopes names, read from the tree."""

from __future__ import annotations

from collections.abc import Mapping

from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.domain.strategy.organism_scope import dataset_leaf, output_organisms


def scope_text(scope: set[str]) -> str:
    return ", ".join(sorted(scope))


def _path_to(node: StrategyStepNode, step_id: str) -> list[StrategyStepNode] | None:
    """The nodes from this one down to the step, the step last."""
    if node.id == step_id:
        return [node]
    for child in node.inputs():
        below = _path_to(child, step_id)
        if below is not None:
            return [node, *below]
    return None


def _transforms_above(
    root: StrategyStepNode,
    combine: StrategyStepNode,
    marked: Mapping[str, str],
    datasets: Mapping[str, frozenset[str]],
) -> list[tuple[str, set[str]]]:
    """The transforms the combine sits under that change the organism, nearest
    first. A transform beside the combine cannot hold the combine's criteria."""
    found: list[tuple[str, set[str]]] = []
    for node in reversed(_path_to(root, combine.id) or []):
        source = node.primary_input
        if node.infer_kind() != "transform" or source is None:
            continue
        output = output_organisms(node, marked, datasets)
        if output is not None and output != output_organisms(source, marked, datasets):
            found.append((node.search_name, output))
    return found


def _dataset_remedy(
    combine: StrategyStepNode,
    scopes: tuple[set[str], set[str]],
    marked: Mapping[str, str],
    datasets: Mapping[str, frozenset[str]],
) -> str | None:
    """The transform that maps a side whose dataset fixes its organism, or None
    when no side runs on a dataset."""
    leaves = [dataset_leaf(side, marked, datasets) for side in combine.inputs()]
    if all(leaf is not None for leaf in leaves):
        return (
            "Each side runs on an experiment, and no parameter changes its "
            "organism. Map one side to the organism of the other with a "
            "GenesByOrthologs transform."
        )
    for leaf, own, other in zip(leaves, scopes, reversed(scopes), strict=True):
        if leaf is not None:
            return (
                f"The {leaf.search_name} search runs on an experiment of "
                f"{scope_text(own)}, and no parameter changes that organism. "
                f"Map that side to {scope_text(other)} with a GenesByOrthologs "
                f"transform."
            )
    return None


def remedy_for(
    root: StrategyStepNode,
    combine: StrategyStepNode,
    scopes: tuple[set[str], set[str]],
    marked: Mapping[str, str],
    datasets: Mapping[str, frozenset[str]],
) -> str:
    """The edit that makes the two scopes meet."""
    for search_name, output in _transforms_above(root, combine, marked, datasets):
        for side in scopes:
            if output == side:
                return (
                    f"Move the {scope_text(side)} criteria above the "
                    f"{search_name} transform."
                )
    by_dataset = _dataset_remedy(combine, scopes, marked, datasets)
    if by_dataset is not None:
        return by_dataset
    return (
        f"Scope every seed to one organism: {scope_text(scopes[0])} or "
        f"{scope_text(scopes[1])}."
    )
