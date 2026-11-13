"""The seed a generated strategy name records, and whether the strategy still holds it."""

from __future__ import annotations

from collections.abc import Collection

from veupathdb.domain.strategy import StrategyAst

from strategist.domain.strategy.ast_diff import nodes_of
from strategist.domain.strategy.step_words import StepWords

__all__ = ["NameSeed", "name_outdated", "name_seed", "title_text"]

type NameSeed = dict[str, dict[str, str]]


def name_seed(ast: StrategyAst | None) -> NameSeed:
    """The wire value of each parameter of every step but a combine, by step id."""
    return {
        step_id: {name: value.to_wire() for name, value in node.parameters.items()}
        for step_id, node in nodes_of(ast).items()
        if node.infer_kind() != "combine"
    }


def name_outdated(seed: NameSeed, now: StrategyAst | None) -> bool:
    """Whether a seed step is gone, or holds another value than its seed."""
    live = name_seed(now)
    return any(
        step_id not in live
        or any(live[step_id].get(name) != wire for name, wire in values.items())
        for step_id, values in seed.items()
    )


def title_text(now: StrategyAst | None, organisms: Collection[str] = ()) -> str:
    """The text a new name is generated from: the organisms, then the words of
    each step left. Empty when no step is left."""
    nodes = nodes_of(now)
    if now is None or not nodes:
        return ""
    texts = StepWords.of(now).criterion_texts
    words = dict.fromkeys(
        texts.get(step_id) or nodes[step_id].display_label for step_id in name_seed(now)
    )
    stated = "; ".join(words)
    return f"{', '.join(sorted(organisms))}: {stated}" if organisms else stated
