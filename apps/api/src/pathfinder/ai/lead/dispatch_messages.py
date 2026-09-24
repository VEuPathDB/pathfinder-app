"""What the Lead is told when a dispatch cannot proceed.

Pure renderings of an ``OperationalSpec`` that a run ran out of budget on, that
a new pass continues, or whose account of an edit does not match what changed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from veupathdb.domain.parameters import to_wire

from pathfinder.ai.agents.criterion_lines import criterion_label, criterion_runs
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.domain.strategy.constraints import OpenQuestion
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    carried_values,
    structure_criteria,
)
from pathfinder.domain.strategy.spec_diff import CriterionChange, SpecDiff


def frame_result_from_draft(spec: OperationalSpec | None) -> FrameResult:
    """Report a run that ran out of budget by what it managed to bind.

    Every criterion is written into the shared draft as it is bound, so the
    work is there to report. Saying "no result" discards a usable turn.
    """
    bound = [c for c in (spec.criteria if spec else []) if c.bound]
    if not bound:
        return FrameResult(
            disposition="needs_user",
            summary=(
                "FRAME ran out of its tool budget with no criteria bound. "
                "Narrow the goal or state fewer criteria, then try again."
            ),
        )
    names = ", ".join(c.id for c in bound)
    return FrameResult(
        disposition="needs_user",
        summary=(
            f"FRAME ran out of its tool budget after binding {len(bound)} "
            f"criteria ({names}). They are kept. Ask it to continue with the "
            f"rest rather than starting again."
        ),
    )


_CONTINUE = "Continue it; this is not a fresh frame."


def budget_stop_work_order(spec: OperationalSpec, prompt: str) -> str:
    """The order for a pass that continues a draft a stopped pass bound.

    The bound criteria are printed so the pass spends its calls on the rest
    instead of paying again for what the earlier pass bound.
    """
    bound = [c for c in spec.criteria if c.bound or c.pending_analysis]
    lines = [
        f"FRAME work order: the previous pass ran out of its tool budget. {_CONTINUE}",
        f"User's goal: {prompt}",
        "",
        (
            f"{len(bound)} criteria are bound already and stay exactly as they are. "
            "Do NOT call set_criterion for any of them:"
        ),
        *_bound_lines(bound),
        *_unbound_lines(spec.criteria),
        "",
        (
            "Bind what the goal states and the lists above do not cover, set "
            "the structure over every criterion, and return a FrameResult."
        ),
    ]
    return "\n".join(lines)


def answered_question_work_order(
    spec: OperationalSpec,
    goal: str,
    questions: Sequence[OpenQuestion],
    *,
    answer: str,
    brief: str,
) -> str:
    """The order for a pass that resolves the answer to its draft's question."""
    heading = (
        "FRAME work order: the previous pass ended with a question the "
        f"researcher has now answered. {_CONTINUE}"
    )
    stated = answered_lines(questions, answer)
    return _resumed_work_order(spec, heading, goal, "answer", stated, brief)


def answered_lines(questions: Sequence[OpenQuestion], answer: str) -> list[str]:
    """Each question an answer closed, then the words of the answer."""
    return [*(f"Question asked: {q.question}" for q in questions), f"Answer: {answer}"]


def earlier_turn_work_order(
    spec: OperationalSpec, goal: str, *, message: str, brief: str
) -> str:
    """The order for a pass that a new message opens over an unbuilt draft."""
    heading = (
        "FRAME work order: an earlier turn bound the criteria below and no "
        f"strategy is built from them yet. {_CONTINUE}"
    )
    stated = [f"The user's message: {message}"]
    return _resumed_work_order(spec, heading, goal, "message", stated, brief)


def _bound_lines(bound: Sequence[Criterion]) -> list[str]:
    return [
        f"- [{c.id}] {criterion_label(c, 80)} -> {criterion_runs(c)}" for c in bound
    ]


def _unbound_lines(criteria: Sequence[Criterion]) -> list[str]:
    unbound = [c for c in criteria if not c.bound and not c.pending_analysis]
    if not unbound:
        return []
    return [
        "",
        "These criteria are recorded and still need a search:",
        *(f"- [{c.id}] {c.text[:80]}" for c in unbound),
    ]


def _resumed_work_order(
    spec: OperationalSpec,
    heading: str,
    goal: str,
    said: str,
    stated: Sequence[str],
    brief: str,
) -> str:
    """The continuation a user's words open over a draft still unbuilt.

    Only the criteria the words concern move, so a criterion bound and not
    named costs the pass no search and no binding.
    """
    done = [
        c
        for c in spec.criteria
        if (c.bound or c.pending_analysis) and not c.open_params
    ]
    waiting = [c for c in spec.criteria if c.bound and c.open_params]
    lines = [
        heading,
        f"User's goal: {goal}",
        "",
        (
            f"{len(done)} criteria are bound already. Do NOT call "
            "search_for_searches or set_criterion for any of them unless the "
            f"{said} below names it:"
        ),
        *_bound_lines(done),
    ]
    if waiting:
        lines.extend(
            [
                "",
                f"These criteria hold open parameters the {said} may decide:",
                *(
                    f"- [{c.id}] {c.text[:80]} -> {c.search_name} (open: "
                    f"{', '.join(slot.param_name for slot in c.open_params)})"
                    for c in waiting
                ),
            ],
        )
    lines.extend(_unbound_lines(spec.criteria))
    lines.append("")
    lines.extend(stated)
    if brief:
        lines.append(f"The Lead's brief: {brief}")
    lines.extend(
        [
            "",
            (
                f"Resolve the {said} by binding or dropping ONLY the criteria it "
                "concerns. Every other bound criterion stays exactly as it is: "
                'state "kept" for it in `changes`. Set the structure over every '
                "criterion and return a FrameResult."
            ),
        ],
    )
    return "\n".join(lines)


_RECORDING_TOOLS = "set_criterion, set_structure, drop_criterion"


def frame_claimed_more_than_it_bound(summary: str) -> str:
    """Why a ``spec_ready`` over a draft with no bound criterion is refused.

    A summary changes no state, so a pass that wrote one and nothing else has
    framed nothing.
    """
    return (
        f"FRAME reported spec_ready with the summary {summary[:200]!r}, and the "
        "spec holds no bound criterion, so the pass recorded nothing. Dispatch "
        f"frame_problem again and tell it to record its work with "
        f"{_RECORDING_TOOLS}; a summary alone binds no search."
    )


# How many of the pass's questions the refusal prints back to it.
_ASKED_WINDOW = 4


def _holds_an_open_slot(spec: OperationalSpec) -> bool:
    return bool(spec.open_slots) or any(c.open_params for c in spec.criteria)


def questions_that_bind_to_nothing(
    questions: Sequence[OpenQuestion],
    draft: OperationalSpec,
    found: OperationalSpec | None,
) -> str:
    """Why a pass that stops on the user asks about nothing it recorded.

    An answer lands in an open slot, so a pass that leaves no slot gives the
    next turn nothing to bind the answer into. Returns an empty string when the
    draft holds a slot the questions can be about.
    """
    if not questions:
        return ""
    if found is not None and draft == found:
        reason = "the spec is exactly as this dispatch found it"
    elif not _holds_an_open_slot(draft):
        reason = "no criterion of the spec holds an open slot"
    else:
        return ""
    asked = "; ".join(q.question for q in questions[:_ASKED_WINDOW])
    return (
        f"FRAME ended needs_user with {len(questions)} question(s) ({asked}) and "
        f"{reason}, so an answer has nowhere to land and the next turn reads no "
        f"criterion to bind it into. Call set_criterion for the criterion each "
        f"question is about, with its search, the values you already have, and "
        f"null for every parameter the user must decide, which records that "
        f"parameter as an open slot. A question about which strategy the user "
        f"saved is recorded the same way: call set_criterion with "
        f"saved_strategy set to the name the user gave, which records the "
        f"saved_strategy slot with the names the listing holds. Then end "
        f"needs_user with the same questions."
    )


def frame_bound_nothing_result() -> FrameResult:
    """Report a second pass that claimed a ready spec and bound nothing."""
    return FrameResult(
        disposition="needs_user",
        summary=(
            "FRAME reported a ready spec twice over a draft with no bound "
            "criterion, so nothing is framed. Ask the user which filters the "
            "strategy must carry, or state fewer criteria and dispatch "
            "frame_problem again."
        ),
    )


def _answered_slots(before: Criterion | None) -> set[str]:
    """The parameters the baseline left open with no value of their own."""
    if before is None:
        return set()
    open_names = {slot.param_name for slot in before.open_params}
    return open_names - set(before.resolved_params)


def _movement_beyond_the_open_slots(
    change: CriterionChange, before: Criterion | None
) -> str:
    """What this change did besides answering the parameters left open.

    A parameter the baseline left open holds no value to re-bind, so answering
    it is the work the turn asked for. Every other movement - another value, a
    value taken away, another search - re-binds a criterion declared kept.
    """
    answered = _answered_slots(before)
    moved = [
        f"{name}={value}"
        for name, value in sorted(change.changed_params.items())
        if name not in answered
    ]
    moved.extend(f"{name} removed" for name in change.removed_params)
    if change.rebound_search:
        moved.append("its search name changed")
    return ", ".join(moved)


def undeclared_spec_changes(
    computed: SpecDiff,
    declared: Sequence[CriterionChange],
    before: OperationalSpec,
) -> str:
    """Where the pass's own account of an edit disagrees with what it did.

    Returns an empty string when every criterion the turn started with is
    accounted for. A silent drop and a silent re-binding are the two shapes
    that reach the user as a strategy they did not ask for.
    """
    stated = {c.criterion_id: c.disposition for c in declared}
    held = {c.id: c for c in before.criteria}
    problems: list[str] = []
    for change in computed.changes:
        cid = change.criterion_id
        if change.disposition == "dropped" and stated.get(cid) != "dropped":
            text = held[cid].text[:80] if cid in held else ""
            problems.append(
                f"{cid} ({text}) is gone from the spec and "
                f"you declared it {stated.get(cid) or 'nothing'}"
            )
        elif change.disposition == "changed" and stated.get(cid) == "kept":
            moved = _movement_beyond_the_open_slots(change, held.get(cid))
            if not moved:
                continue
            problems.append(f"{cid} is declared kept but its binding moved ({moved})")
    if not problems:
        return ""
    return (
        "This turn edits a spec that already had "
        f"{len(before.criteria)} criteria, and the account of it does not match "
        f"what happened: {'; '.join(problems)}. Nothing was applied: the "
        "strategy is exactly as this turn found it. A criterion the request "
        "does not mention is kept and must keep the values the workspace "
        "shows; re-bind it with set_criterion using those values, or drop it "
        "with drop_criterion and say why."
    )


def option_binds_no_step_message(spec: OperationalSpec, unplaced: Sequence[str]) -> str:
    """Why a spec whose option no single step carries is refused.

    WDK holds a choice inside a search as a value in that search's parameters,
    so an option belongs to exactly one criterion that runs the search.
    """
    named = structure_criteria(spec.structure)
    carriers: defaultdict[str, list[Criterion]] = defaultdict(list)
    for criterion in spec.criteria:
        if criterion.id in named and criterion.search_name:
            carriers[criterion.search_name].append(criterion)
    wanted = set(unplaced)
    problems = [
        _unplaced_option(criterion, carriers[criterion.search_name])
        for criterion in spec.criteria
        if criterion.id in wanted
    ]
    return (
        f"The build cannot place the value(s) these criteria state: "
        f"{'; '.join(problems)}. Nothing was built and the strategy is "
        f"unchanged. A choice inside a search is a value in that search's own "
        f"parameters: call set_criterion on the criterion that runs the "
        f"search, with the value in its params, and drop_criterion on the one "
        f"that states it alone. A criterion that runs a search of its own "
        f"belongs in set_structure instead."
    )


def _unplaced_option(option: Criterion, carriers: Sequence[Criterion]) -> str:
    values = ", ".join(sorted(option.resolved_params))
    if not carriers:
        return (
            f"{option.id} ({option.text[:80]}) states {values} on "
            f"{option.search_name}, and no criterion in the structure runs that "
            f"search"
        )
    if len(carriers) == 1:
        return _contradicted_option(option, carriers[0])
    return (
        f"{option.id} ({option.text[:80]}) states {values} on "
        f"{option.search_name}, and {len(carriers)} criteria in the structure "
        f"run that search ({', '.join(c.id for c in carriers)})"
    )


def _contradicted_option(option: Criterion, carrier: Criterion) -> str:
    """Why an option one criterion runs the search for is still unplaced."""
    carried = carried_values(carrier)
    defaulted = set(option.defaulted_params)
    clashes = [
        f"{name}={to_wire(value)} where {carrier.id} already carries "
        f"{name}={carried[name]}"
        for name, value in option.resolved_params.items()
        if name not in defaulted and name in carried and carried[name] != to_wire(value)
    ]
    return (
        f"{option.id} ({option.text[:80]}) states "
        f"{'; '.join(clashes)} on {option.search_name}"
    )
