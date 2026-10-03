"""The most recent change to a strategy: what it did and the result's count
before and after it."""

from __future__ import annotations

from collections.abc import Callable

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from veupathdb import JSONObject
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, walk

from pathfinder.domain.count_words import counted
from pathfinder.domain.strategy.revision import strategy_revision

_BUILT = "built the strategy"
_CHANGED = "changed the strategy"


class LastChange(CamelModel):
    """The strategy's most recent change, and the result's count on each side."""

    model_config = ConfigDict(frozen=True)

    # What the change did, as one clause: "deleted <step>", "built the strategy".
    what: str
    before: int | None = None
    after: int | None = None

    def count(self, side: str) -> int | None:
        """The count on one side, ``before`` or ``after``; None for another word."""
        match side:
            case "before":
                return self.before
            case "after":
                return self.after
            case _:
                return None

    def line(self, noun: str) -> str:
        sides = ", ".join(self._side(side, noun) for side in ("before", "after"))
        return f"Last change: {self.what}; {sides}"

    def _side(self, side: str, noun: str) -> str:
        count = self.count(side)
        return (
            f"count {side} not recorded"
            if count is None
            else f"{counted(count, noun)} {side}"
        )

    def redacted(self, redact: Callable[[str], str]) -> LastChange:
        return self.model_copy(update={"what": redact(self.what)})


def _root_count(ast: StrategyAst) -> int | None:
    return (ast.step_counts or {}).get(ast.root.id)


def _nodes(ast: StrategyAst) -> dict[str, StrategyStepNode]:
    return {
        node.id: node for root in (ast.root, *ast.detached_roots) for node in walk(root)
    }


def _inputs(node: StrategyStepNode) -> tuple[JSONObject, list[str]]:
    """What the step computes from: its own inputs and the ids it reads."""
    own: JSONObject = node.model_dump(
        mode="json",
        exclude={"primary_input", "secondary_input", "display_name", "id"},
    )
    return own, node.input_ids()


def _named(verb: str, nodes: list[StrategyStepNode]) -> list[str]:
    return [f"{verb} {' and '.join(n.display_label for n in nodes)}"] if nodes else []


def _what(previous: StrategyAst, latest: StrategyAst) -> str:
    """The searches the change deleted and added, and the steps it edited. A
    combine that a delete or an add takes with it is not named."""
    was, now = _nodes(previous), _nodes(latest)
    searches = [
        n for n in (*was.values(), *now.values()) if n.infer_kind() != "combine"
    ]
    deleted = [n for n in searches if n.id in was and n.id not in now]
    added = [n for n in searches if n.id in now and n.id not in was]
    edited = [
        node
        for step_id, node in now.items()
        if step_id in was and _inputs(was[step_id]) != _inputs(node)
    ]
    clauses = [
        *_named("deleted", deleted),
        *_named("added", added),
        *_named("edited", edited),
    ]
    return ", ".join(clauses) or _CHANGED


def change_between(previous: StrategyAst | None, latest: StrategyAst) -> LastChange:
    """The change from ``previous`` to ``latest``; no previous tree is a build."""
    return LastChange(
        before=None if previous is None else _root_count(previous),
        after=_root_count(latest),
        what=_BUILT if previous is None else _what(previous, latest),
    )


def change_since(
    found: StrategyAst | None, found_change: LastChange | None, live: StrategyAst | None
) -> LastChange | None:
    """The last change as of the live tree. ``found`` is the tree the message
    found and ``found_change`` the change that made it; a tree the turn did not
    move keeps that change, with the live count after it."""
    if live is None:
        return None
    if found is not None and strategy_revision(found) == strategy_revision(live):
        if found_change is None:
            return None
        return found_change.model_copy(update={"after": _root_count(live)})
    return change_between(found, live)


__all__ = ["LastChange", "change_between", "change_since"]
