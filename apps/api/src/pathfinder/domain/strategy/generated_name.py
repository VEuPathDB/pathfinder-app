"""Whether a generated strategy name still states what the strategy applies."""

from __future__ import annotations

from collections.abc import Collection

from veupathdb.domain.parameters import MultiPickValue, ParamValue, to_wire
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from pathfinder.domain.strategy.ast_diff import nodes_of
from pathfinder.domain.strategy.step_naming import states_the_wire_form
from pathfinder.domain.strategy.step_words import StepWords

__all__ = ["name_outdated", "name_seed", "named_steps"]


def named_steps(ast: StrategyAst | None) -> list[str]:
    """The steps a generated name is written over: every step but a combine."""
    return [
        step_id
        for step_id, node in nodes_of(ast).items()
        if node.infer_kind() != "combine"
    ]


def _terms(value: ParamValue) -> set[str]:
    match value:
        case MultiPickValue(values=terms):
            return set(terms)
        case _:
            return {to_wire(value)}


def _held(node: StrategyStepNode, parameter: str) -> set[str]:
    value = node.parameters.get(parameter)
    return set() if value is None else _terms(value)


def _left(before: StrategyStepNode, after: StrategyStepNode) -> set[str]:
    """The terms the step held before and holds no longer."""
    return {
        term
        for parameter in before.parameters
        for term in _held(before, parameter) - _held(after, parameter)
        if term.strip()
    }


def name_outdated(
    name: str,
    marked: Collection[str],
    *,
    start: StrategyAst | None,
    now: StrategyAst | None,
) -> bool:
    """Whether a marked step is gone, or left a value the name states.

    A value counts when the name carries it as a whole word, in any case.
    """
    was, live = nodes_of(start), nodes_of(now)
    if any(step_id not in live for step_id in marked):
        return True
    folded = name.casefold()
    return any(
        states_the_wire_form(folded, term.casefold())
        for step_id in marked
        if step_id in was
        for term in _left(was[step_id], live[step_id])
    )


def name_seed(now: StrategyAst | None, organisms: Collection[str] = ()) -> str:
    """The text a new name is generated from: the organisms, then the words of
    each step left. Empty when no step is left."""
    nodes = nodes_of(now)
    if now is None or not nodes:
        return ""
    texts = StepWords.of(now).criterion_texts
    words = dict.fromkeys(
        texts.get(step_id) or nodes[step_id].display_label
        for step_id in named_steps(now)
    )
    stated = "; ".join(words)
    return f"{', '.join(sorted(organisms))}: {stated}" if organisms else stated
