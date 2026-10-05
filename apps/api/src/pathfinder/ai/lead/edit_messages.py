"""What an edit dispatch says: its work order, and why it refuses.

Prose only. The values a criterion already holds are printed here because a
pass that cannot see them re-derives them from a sentence.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from pydantic import BaseModel, ConfigDict
from veupathdb.domain.parameters import to_wire

from pathfinder.ai.agents.criterion_lines import criterion_label, criterion_runs
from pathfinder.ai.graph.turn_records import AnsweredQuestions, NamedStep
from pathfinder.ai.lead.dispatch_messages import (
    answered_lines,
    asks_lines,
    refusal_lines,
    stop_heading,
)
from pathfinder.ai.lead.phase_stop import PhaseStop
from pathfinder.domain.strategy.named_combine import NamedCombine, combine_at
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    StructureNode,
    criteria_under,
)
from pathfinder.domain.strategy.spec_diff import CriterionChange, SpecDiff

__all__ = [
    "EditMessage",
    "changed_revision_message",
    "delta_disagrees_with_the_strategy_message",
    "edit_bound_nothing_message",
    "edit_continuation_work_order",
    "edit_moves_nothing_message",
    "edit_operation_refused_message",
    "edit_work_order",
    "no_earlier_revision_message",
    "no_strategy_to_edit_message",
    "nothing_to_undo_message",
    "recut_call",
    "removal_is_the_cards_message",
    "undo_moves_nothing_message",
    "unsupported_edit_message",
    "wdk_refused_the_written_step_message",
]


class EditMessage(BaseModel):
    """The researcher's message an edit pass answers: its words, the asks the
    Lead answers, and the questions of an earlier pass it answers."""

    model_config = ConfigDict(frozen=True)

    prompt: str
    asks: tuple[str, ...] = ()
    answer: AnsweredQuestions | None = None


def pending_lines(
    pending: SpecDiff, before: OperationalSpec, answered: OperationalSpec
) -> list[str]:
    """What an earlier pass of this thread stated and no push has applied.

    Each line names one criterion the plan and the strategy disagree about, so
    the pass that follows can let it stand or take it back.
    """
    if not pending.changes:
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
            "NOT PUSHED YET. An earlier pass of this conversation stated these and "
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
        was = {name: to_wire(value) for name, value in held[cid].param_values.items()}
        running = ", ".join(
            f"{name}={was.get(name, '(unset)')}" for name in change.changed_params
        )
        return f"- [{cid}] states {moved}; the strategy runs {running}."
    return ""


def edit_work_order(
    reason: str,
    message: EditMessage,
    before: OperationalSpec,
    *,
    pending: SpecDiff,
    answered: OperationalSpec,
) -> str:
    """The FRAME work order for an edit, carrying every bound value.

    A message that answers what an earlier pass asked carries the questions
    it answers, so the pass reads the answer against them.
    """
    prompt, answer = message.prompt, message.answer
    lines = [
        f"EDIT work order: {reason}",
        f"The user's message: {prompt}",
        *asks_lines(message.asks),
        *(
            [
                "The message answers what the previous pass asked:",
                *answered_lines(answer.questions, answer.answer),
            ]
            if answer is not None
            else []
        ),
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
        *_named_combine_lines(before, prompt),
        f"The strategy holds {len(before.criteria)} criteria now:",
    ]
    for criterion in before.criteria:
        lines.append(
            f"- [{criterion.id}] {criterion_label(criterion, 80)} -> "
            f"{criterion_runs(criterion)} ({criterion.role})"
        )
        lines.extend(
            f"    {name}={to_wire(value)}"
            for name, value in criterion.param_values.items()
        )
    lines.extend(pending_lines(pending, before, answered))
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
    message: EditMessage,
    *,
    pending: SpecDiff,
    answered: OperationalSpec,
    stop: PhaseStop,
) -> str:
    """The work order for the pass that continues a stopped edit.

    An edit owes a disposition for every criterion the turn started with, so
    the continuation is the edit work order and not a fresh frame.
    """
    return edit_work_order(
        " ".join([f"{stop_heading(stop)}; continue that edit", *refusal_lines(stop)]),
        message,
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


def _named_combine_lines(before: OperationalSpec, prompt: str) -> list[str]:
    """The combine the message names by its place, as a node of the shape."""
    named = NamedCombine.read(prompt)
    node = (
        None
        if named is None or before.structure is None
        else combine_at(before.structure, named.position)
    )
    if named is None or node is None:
        return []
    members = ", ".join(sorted(criteria_under(node)))
    return [
        (
            f"The message names the {named.position} combine, the "
            f"{node.combine_operator.value} over {members}: make it "
            f"{named.operator.value}, and keep every other combine's operator as "
            f"it stands."
        ),
        "",
    ]


def _shape_node(
    node: StructureNode,
    by_id: dict[str, Criterion],
    depth: int,
    lines: list[str],
) -> None:
    pad = "  " * depth
    if node.kind == "combine":
        lines.append(f"{pad}{node.combine_operator}")
    elif node.kind == "copy":
        lines.append(f"{pad}COPY")
    else:
        prefix = "TRANSFORM " if node.kind == "transform" else ""
        lines.append(f"{pad}{prefix}{_criterion_label(node.named_criterion, by_id)}")
    for child in node.inputs:
        _shape_node(child, by_id, depth + 1, lines)


def _criterion_label(criterion_id: str, by_id: dict[str, Criterion]) -> str:
    criterion = by_id.get(criterion_id)
    if criterion is None:
        return f"[{criterion_id}] (no criterion states this step)"
    return f"[{criterion.id}] {criterion.text[:40]}"


def no_strategy_to_edit_message(offered: Collection[str]) -> str:
    """The refusal of an edit on a thread with no step, naming offered tools."""
    refusal = "edit_strategy needs a strategy to edit, and this conversation has none."
    if "frame_problem" in offered:
        return (
            f"{refusal} Call frame_problem to operationalize the goal, then "
            "build_strategy."
        )
    return f"{refusal} Call build_strategy to build the spec this turn framed."


def edit_bound_nothing_message() -> str:
    return (
        "The edit pass left no spec behind, so there is nothing to compare "
        "against the strategy. Nothing was applied: the strategy is exactly as "
        "this turn found it. Dispatch edit_strategy again and tell it to "
        "record its work with set_criterion and drop_criterion."
    )


def recut_call(exports: Sequence[str]) -> str:
    """The call that recuts one of the strategy's analysis exports."""
    ids = " or ".join(f"'{step_id}'" for step_id in exports)
    if len(exports) == 1:
        return f"create_eda_step(replace_step_id={ids})"
    return f"create_eda_step(replace_step_id=<one of {ids}>)"


def edit_moves_nothing_message(exports: Sequence[str]) -> str:
    """What an edit that moves no step says, naming the recut of any analysis
    export the strategy holds: FRAME binds no export's cut."""
    if not exports:
        return "The strategy already states everything the edit asks for."
    return (
        "The edit changes no step FRAME binds: FRAME keeps an analysis export as it "
        f"is. A change to the export's thresholds or direction is {recut_call(exports)}, "
        "which reads the completed compute again; new groups run run_eda_compute "
        "first. That recut is the change the researcher asked for, so it needs no "
        "card: make it. Any other request the strategy already states."
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


def changed_revision_message(base_revision: str, current: str) -> str:
    return (
        f"The strategy changed while this edit was being planned (it was "
        f"{base_revision!r} and is now {current!r}). Nothing was applied. Call "
        f"get_live_strategy_state to read it as it is now, then decide whether "
        f"the edit still applies."
    )


def removal_is_the_cards_message(removed: Mapping[str, NamedStep]) -> str:
    """Why an edit whose only change removes built steps is sent to the card.

    The researcher approves every removal on the delete card, so an edit pass
    never takes a step off the strategy on its own.
    """
    named = ", ".join(f"[{sid}] {step.described()}" for sid, step in removed.items())
    held = (
        "Nothing was applied: the strategy still holds every step and every "
        "value it held before this edit."
    )
    rule = "Do not dispatch edit_strategy to remove a step."
    if len(removed) == 1:
        (step_id,) = removed
        return (
            f"This edit only removes {named}, and a removal is the researcher's "
            f'to approve. {held} Call delete_step with step_id "{step_id}"; its '
            f"card names the step and the researcher approves it. {rule}"
        )
    ids = ", ".join(f'"{sid}"' for sid in removed)
    return (
        f"This edit only removes each of {named}, and a removal is the "
        f"researcher's to approve. {held} Call delete_step once for each of "
        f"step_id {ids}, one card at a time; each card names its step and the "
        f"researcher approves it. {rule}"
    )


def nothing_to_undo_message() -> str:
    """The failure of an undo over a strategy already at its previous revision."""
    return (
        "Nothing to undo: the strategy is the one before the last change. Tell "
        "the researcher so, and change nothing."
    )


def no_earlier_revision_message() -> str:
    """The failure of an undo on a thread with no strategy before the last change."""
    return (
        "Nothing to undo: the conversation holds no strategy before the last change. "
        "Removing the strategy is clear_strategy, on the researcher's word."
    )


def undo_moves_nothing_message() -> str:
    """The failure of an undo whose previous revision no criterion can state."""
    return (
        "Nothing to undo that an edit can state: the strategy before the last "
        "change differs from this one only in values no criterion states. Tell "
        "the researcher so, and change nothing."
    )
