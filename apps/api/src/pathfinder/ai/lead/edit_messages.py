"""What an edit dispatch says: its work order, and why it refuses.

Prose only. The values a criterion already holds are printed here because a
pass that cannot see them re-derives them from a sentence.
"""

from __future__ import annotations

from veupathdb.domain.parameters import to_wire

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    StructureNode,
)

__all__ = [
    "changed_revision_message",
    "edit_bound_nothing_message",
    "edit_continuation_work_order",
    "edit_work_order",
    "no_strategy_to_edit_message",
    "unsupported_edit_message",
]


def edit_work_order(reason: str, prompt: str, before: OperationalSpec) -> str:
    """The FRAME work order for an edit, carrying every bound value."""
    lines = [
        f"EDIT work order: {reason}",
        f"The user's message: {prompt}",
        "",
        (
            "This turn EDITS the strategy below; it is not a fresh frame. State a "
            'disposition in `changes` for EVERY criterion listed here: "kept", '
            '"changed" (name the parameters the request moves in `changed_params`) '
            'or "dropped" (with a `reason`).'
        ),
        "",
        (
            "A criterion the request does not name is kept: do not call "
            "set_criterion for it, and its values below stay byte for byte. For a "
            "criterion the request DOES change, call set_criterion with the values "
            "below as the `params` object plus the requested override, so only the "
            "named parameter moves and every other value is copied rather than "
            "re-derived from the text."
        ),
        "",
        *_shape_lines(before),
        f"The strategy holds {len(before.criteria)} criteria now:",
    ]
    for criterion in before.criteria:
        lines.append(
            f"- [{criterion.id}] {criterion.text[:80]} -> "
            f"{criterion.search_name or '(UNBOUND)'} ({criterion.role})"
        )
        lines.extend(
            f"    {name}={to_wire(value)}"
            for name, value in criterion.resolved_params.items()
        )
    lines.extend(
        [
            "",
            (
                "A request that changes how the steps COMBINE is a structure "
                "change, not a criterion change: call set_structure with the whole "
                "new tree over the same criterion ids printed above, and state "
                '"kept" for every criterion the request does not otherwise touch. '
                "Each leaf keeps its step and its WDK id; only the combines above "
                "them are rebuilt. The tree states every criterion the spec keeps "
                "and no step the strategy does not hold."
            ),
            "",
            "Return a FrameResult with `changes` filled in.",
        ]
    )
    return "\n".join(lines)


def edit_continuation_work_order(before: OperationalSpec, prompt: str) -> str:
    """The work order for the pass that continues an edit stopped by its budget.

    An edit owes a disposition for every criterion the turn started with, so
    the continuation is the edit work order and not a fresh frame.
    """
    return edit_work_order(
        "the previous pass ran out of its tool budget; continue that edit",
        prompt,
        before,
    )


def _shape_lines(before: OperationalSpec) -> list[str]:
    """The shape the strategy holds now, as an indented tree."""
    if before.structure is None:
        return []
    by_id = {c.id: c for c in before.criteria}
    lines = ["The shape the strategy has now:"]
    _shape_node(before.structure.root, by_id, 1, lines)
    lines.append("")
    return lines


def _shape_node(
    node: StructureNode,
    by_id: dict[str, Criterion],
    depth: int,
    lines: list[str],
) -> None:
    pad = "  " * depth
    if node.kind == "combine":
        lines.append(f"{pad}{node.operator or 'COMBINE'}")
    else:
        prefix = "TRANSFORM " if node.kind == "transform" else ""
        lines.append(f"{pad}{prefix}{_criterion_label(node.criterion_id, by_id)}")
    for child in node.inputs:
        _shape_node(child, by_id, depth + 1, lines)


def _criterion_label(criterion_id: str | None, by_id: dict[str, Criterion]) -> str:
    criterion = by_id.get(criterion_id or "")
    if criterion is None:
        return f"[{criterion_id}] (no criterion states this step)"
    return f"[{criterion.id}] {criterion.text[:40]}"


def no_strategy_to_edit_message() -> str:
    return (
        "edit_strategy needs a strategy to edit, and this thread has none. Call "
        "frame_problem to operationalize the goal, then build_strategy."
    )


def edit_bound_nothing_message() -> str:
    return (
        "The edit pass left no spec behind, so there is nothing to compare "
        "against the strategy. Dispatch edit_strategy again and tell it to "
        "record its work with set_criterion and drop_criterion."
    )


def unsupported_edit_message(detail: str) -> str:
    return (
        f"This edit does not map onto the strategy's steps: {detail}. A new "
        f"shape states every criterion the spec keeps, states no step from "
        f"outside this strategy, and leaves no step disconnected. Call "
        f"edit_strategy again with a structure over the criterion ids the "
        f"strategy holds, or tell the user what the request would cost and ask "
        f"before anything is replaced."
    )


def changed_revision_message(base_revision: str, current: str) -> str:
    return (
        f"The strategy changed while this edit was being planned (it was "
        f"{base_revision!r} and is now {current!r}). Nothing was applied. Call "
        f"get_live_strategy_state to read it as it is now, then decide whether "
        f"the edit still applies."
    )
