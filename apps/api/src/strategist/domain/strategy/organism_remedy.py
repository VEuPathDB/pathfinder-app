"""The edit a refused INTERSECT of two organism scopes names, read from the tree."""

from __future__ import annotations

from collections.abc import Mapping

from veupathdb.domain.strategy import StrategyStepNode, walk

from strategist.domain.strategy.organism_scope import output_organisms


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


def _experiments(
    side: StrategyStepNode, datasets: Mapping[str, frozenset[str]]
) -> list[str]:
    if output_organisms(side, {}, datasets) is None:
        return []
    return sorted(
        {
            node.search_name
            for node in walk(side)
            if node.id in datasets
            and output_organisms(
                side, {}, {k: v for k, v in datasets.items() if k != node.id}
            )
            is None
        }
    )


def _dataset_remedy(
    combine: StrategyStepNode,
    scopes: tuple[set[str], set[str]],
    datasets: Mapping[str, frozenset[str]],
) -> str | None:
    """The transform that maps a side whose datasets fix its organism, or None
    when a parameter states some of the organism of each side."""
    sides = [_experiments(side, datasets) for side in combine.inputs()]
    if all(sides):
        return (
            "Each side runs on an experiment, and no parameter changes its "
            "organism. Map one side to the organism of the other with a "
            "GenesByOrthologs transform."
        )
    for searches, own, other in zip(sides, scopes, reversed(scopes), strict=True):
        if searches:
            runs = (
                "searches run on experiments"
                if len(searches) > 1
                else "search runs on an experiment"
            )
            return (
                f"The {', '.join(searches)} {runs} of {scope_text(own)}, and no "
                f"parameter changes that organism. Map that side to "
                f"{scope_text(other)} with a GenesByOrthologs transform."
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
    by_dataset = _dataset_remedy(combine, scopes, datasets)
    if by_dataset is not None:
        return by_dataset
    return (
        f"Scope every seed to one organism: {scope_text(scopes[0])} or "
        f"{scope_text(scopes[1])}."
    )
