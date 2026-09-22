"""What an edit dispatch says: its work order, and why it refuses.

Prose only. The values a criterion already holds are printed here because a
pass that cannot see them re-derives them from a sentence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from veupathdb.domain.parameters import to_wire

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    StructureNode,
)
from pathfinder.domain.strategy.spec_diff import CriterionChange, SpecDiff

__all__ = [
    "changed_revision_message",
    "delta_disagrees_with_the_strategy_message",
    "edit_bound_nothing_message",
    "edit_continuation_work_order",
    "edit_operation_refused_message",
    "edit_work_order",
    "no_strategy_to_edit_message",
    "pending_changes_no_pass_accounted_for_message",
    "unsupported_edit_message",
    "wdk_refused_the_written_step_message",
]


def pending_lines(
    pending: SpecDiff, before: OperationalSpec, answered: OperationalSpec | None
) -> list[str]:
    """What an earlier pass of this thread stated and no push has applied.

    Each line names one criterion the plan and the strategy disagree about, so
    the pass that follows can let it stand or take it back.
    """
    if not pending.changes or answered is None:
        return []
    planned = {c.id: c for c in before.criteria}
    held = {c.id: c for c in answered.criteria}
    lines = [
        found
        for change in pending.changes
        if (found := _pending_line(change, planned, held))
    ]
    if not lines:
        return []
    return [
        "",
        (
            "NOT PUSHED YET. An earlier pass of this thread stated these and "
            "the strategy does not hold them. State a disposition in `changes` "
            "for each of them too: repeat it to let it stand, or take it back "
            "by stating the criterion the strategy holds with set_criterion."
        ),
        *lines,
    ]


def _pending_line(
    change: CriterionChange,
    planned: Mapping[str, Criterion],
    held: Mapping[str, Criterion],
) -> str:
    """One pending change, named by what the strategy would have to do."""
    cid = change.criterion_id
    if change.disposition == "dropped":
        criterion = held[cid]
        return (
            f"- [{cid}] {criterion.text[:60]} is dropped in this spec and the "
            f"strategy still runs it."
        )
    if change.disposition == "added":
        return f"- [{cid}] {planned[cid].text[:60]} has no step on the strategy yet."
    if change.disposition == "changed":
        moved = ", ".join(
            f"{name}={value}" for name, value in change.changed_params.items()
        )
        was = {
            name: to_wire(value) for name, value in held[cid].resolved_params.items()
        }
        running = ", ".join(
            f"{name}={was.get(name, '(unset)')}" for name in change.changed_params
        )
        return f"- [{cid}] states {moved}; the strategy runs {running}."
    return ""


def edit_work_order(
    reason: str,
    prompt: str,
    before: OperationalSpec,
    *,
    pending: SpecDiff | None = None,
    answered: OperationalSpec | None = None,
) -> str:
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
    lines.extend(pending_lines(pending, before, answered) if pending else [])
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


def edit_continuation_work_order(
    before: OperationalSpec,
    prompt: str,
    *,
    pending: SpecDiff | None = None,
    answered: OperationalSpec | None = None,
) -> str:
    """The work order for the pass that continues an edit stopped by its budget.

    An edit owes a disposition for every criterion the turn started with, so
    the continuation is the edit work order and not a fresh frame.
    """
    return edit_work_order(
        "the previous pass ran out of its tool budget; continue that edit",
        prompt,
        before,
        pending=pending,
        answered=answered,
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
        "against the strategy. Nothing was applied: the strategy is exactly as "
        "this turn found it. Dispatch edit_strategy again and tell it to "
        "record its work with set_criterion and drop_criterion."
    )


def unsupported_edit_message(detail: str) -> str:
    """The shape this edit states does not map onto the steps the strategy holds."""
    return (
        f"This edit does not map onto the strategy's steps: {detail}. Nothing "
        f"was applied: the strategy still holds every step and every value it "
        f"held before this edit. A new shape states every criterion the spec "
        f"keeps, states no step from outside this strategy, and leaves no step "
        f"disconnected. Dispatch edit_strategy again with a structure over the "
        f"criterion ids the strategy holds, or tell the user which part of the "
        f"request the strategy's shape cannot take and stop."
    )


def edit_operation_refused_message(detail: str) -> str:
    """One graph operation this edit writes was refused before the push.

    The refusal is about that operation. VEuPathDB is not asked, and the steps
    the strategy already holds are not judged.
    """
    return (
        f'One operation this edit writes was refused: "{detail}". Nothing was '
        f"applied: the strategy still holds every step and every value it held "
        f"before this edit. Dispatch edit_strategy again and state that "
        f"criterion with set_criterion under a step id the strategy holds, "
        f"drop it with drop_criterion, or tell the user what could not be "
        f"changed and stop. Do not offer to rebuild the strategy from scratch."
    )


def wdk_refused_the_written_step_message(
    detail: str, *, steps: Sequence[str], params: Sequence[str]
) -> str:
    """VEuPathDB turned down the values this edit writes on a step.

    The steps the strategy already held were not judged, so the refusal states
    that and offers the two answers that keep them.
    """
    which = ", ".join(steps) or "the step this edit writes"
    named = f", for {', '.join(params)}" if params else ""
    return (
        f"VEuPathDB refused the values this edit writes on {which}{named}. It "
        f'said: "{detail}". Nothing was applied: the strategy still holds every '
        f"step and every value it held before this edit, and the steps it "
        f"already held are not what VEuPathDB turned down. Dispatch "
        f"edit_strategy again and tell it to bind that criterion with "
        f"set_criterion, using values VEuPathDB accepts for those parameters, "
        f"or tell the user exactly what VEuPathDB refused and stop. Do not "
        f"offer to rebuild the strategy from scratch, and do not drop the "
        f"steps it holds."
    )


def delta_disagrees_with_the_strategy_message(criterion_ids: Sequence[str]) -> str:
    """The account of this edit and the steps it would build disagree.

    Nothing is applied, because the reply is read from the account and the
    researcher cannot check a step the account leaves out.
    """
    named = ", ".join(criterion_ids)
    return (
        f"This edit and its account disagree about {named}: each of them is "
        f"either a criterion the strategy already holds a step for, or one "
        f"this edit would build and the account does not state. Nothing was "
        f"applied. Dispatch edit_strategy again and, for each id named here, "
        f"state a criterion under the step id the strategy holds, or drop it "
        f"with drop_criterion."
    )


def pending_changes_no_pass_accounted_for_message(criterion_ids: Sequence[str]) -> str:
    """Why an edit carrying an earlier pass's unpushed change is refused.

    The reply is read from this edit's own account, so a change no pass of this
    turn stated would reach the strategy with nothing to explain it.
    """
    named = ", ".join(criterion_ids)
    return (
        f"This edit would also carry what an earlier pass of this thread left "
        f"unpushed, and no pass of this turn accounted for {named}. Nothing "
        f"was applied. Dispatch edit_strategy again and, for each id named "
        f"here, state its disposition in `changes` to let it stand, or state "
        f"the criterion the strategy holds with set_criterion to take it back."
    )


def changed_revision_message(base_revision: str, current: str) -> str:
    return (
        f"The strategy changed while this edit was being planned (it was "
        f"{base_revision!r} and is now {current!r}). Nothing was applied. Call "
        f"get_live_strategy_state to read it as it is now, then decide whether "
        f"the edit still applies."
    )
