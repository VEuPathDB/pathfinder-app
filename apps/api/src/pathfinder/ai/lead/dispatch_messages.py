"""What the Lead is told when a dispatch cannot proceed.

Pure renderings of an ``OperationalSpec`` that a run ran out of budget on, that
is not ready to build, or whose account of an edit does not match what changed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from veupathdb.domain.parameters.value_codec import to_wire

from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.phase_stop import PhaseStop
from pathfinder.domain.strategy.build_outcome import BuildOutcome
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


def frame_continuation_work_order(spec: OperationalSpec | None, prompt: str) -> str:
    """The work order for the pass that continues one stopped by its budget.

    The bound criteria are printed so the second pass spends its calls on the
    rest instead of paying again for what the first pass bound.
    """
    criteria = spec.criteria if spec is not None else []
    bound = [c for c in criteria if c.bound]
    unbound = [c for c in criteria if not c.bound]
    lines = [
        (
            "FRAME work order: the previous pass ran out of its tool budget. "
            "Continue it; this is not a fresh frame."
        ),
        f"User's goal: {prompt}",
        "",
        (
            f"{len(bound)} criteria are bound already and stay exactly as they are. "
            "Do NOT call set_criterion for any of them:"
        ),
        *(
            f"- [{c.id}] {c.text[:80]} -> {c.search_name or '(saved strategy)'}"
            for c in bound
        ),
    ]
    if unbound:
        lines.extend(
            [
                "",
                "These criteria are recorded and still need a search:",
                *(f"- [{c.id}] {c.text[:80]}" for c in unbound),
            ],
        )
    lines.extend(
        [
            "",
            (
                "Bind what the goal states and the lists above do not cover, set "
                "the structure over every criterion, and return a FrameResult."
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
    texts = {c.id: c.text for c in before.criteria}
    problems: list[str] = []
    for change in computed.changes:
        cid = change.criterion_id
        if change.disposition == "dropped" and stated.get(cid) != "dropped":
            problems.append(
                f"{cid} ({texts.get(cid, '')[:80]}) is gone from the spec and "
                f"you declared it {stated.get(cid) or 'nothing'}"
            )
        elif change.disposition == "changed" and stated.get(cid) == "kept":
            moved = ", ".join(
                f"{name}={value}"
                for name, value in sorted(change.changed_params.items())
            )
            problems.append(
                f"{cid} is declared kept but its binding moved "
                f"({moved or 'its search name changed'})"
            )
    if not problems:
        return ""
    return (
        "This turn edits a spec that already had "
        f"{len(before.criteria)} criteria, and the account of it does not match "
        f"what happened: {'; '.join(problems)}. A criterion the request does "
        "not mention is kept and must keep the values the workspace shows; "
        "re-bind it with set_criterion using those values, or drop it with "
        "drop_criterion and say why."
    )


def build_would_replace_the_strategy(step_count: int) -> str:
    """Why a build over an existing strategy is refused.

    A build materializes the spec into a new tree, so every WDK step id and
    every value the researcher set on the canvas goes with the old one.
    """
    return (
        f"This thread already has a strategy of {step_count} steps, and "
        f"build_strategy replaces it: every WDK step id changes and any value "
        f"the researcher edited on the canvas is lost. Call edit_strategy to "
        f"change what this strategy asks, which patches only the steps the "
        f"request names. If the request really is to throw this strategy away "
        f"and start over, call clear_strategy, which asks the user to approve "
        f"the deletion before anything is removed."
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
        f"{'; '.join(problems)}. A choice inside a search is a value in that "
        f"search's own parameters: call set_criterion on the criterion that "
        f"runs the search, with the value in its params, and drop_criterion on "
        f"the one that states it alone. A criterion that runs a search of its "
        f"own belongs in set_structure instead."
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


def build_not_ready_message(spec: OperationalSpec | None) -> str:
    """Why the spec cannot be built, phrased for what the model can do next.

    Open parameter slots are not a retry. Re-running FRAME regenerates the
    same slots, so telling the model to "call frame_problem first" sends it
    round a loop it cannot exit -- only the user can answer.
    """
    if spec is None or not spec.criteria or spec.structure is None:
        return (
            "No OperationalSpec to build yet (no criteria or no structure). "
            "Call frame_problem first."
        )
    if spec.open_slots:
        slots = "; ".join(
            f"{slot.param_name}"
            + (f" -- {slot.question}" if slot.question else "")
            + (f" (options: {', '.join(slot.options)})" if slot.options else "")
            for slot in spec.open_slots
        )
        return (
            f"The strategy cannot be built until the user answers "
            f"{len(spec.open_slots)} open parameter(s): {slots}. "
            "Do NOT re-frame -- the same slots come back. Ask the user for "
            "these values in your reply, then build once they answer."
        )
    unbound = [c.id for c in spec.criteria if not c.bound]
    if unbound:
        return (
            f"These criteria are not bound to a WDK search: {', '.join(unbound)}. "
            "Call frame_problem to bind them."
        )
    open_params = [
        f"{c.id}.{slot.param_name}" for c in spec.criteria for slot in c.open_params
    ]
    return (
        f"These criteria still need user-supplied parameters: "
        f"{', '.join(open_params)}. Ask the user for them, then build."
    )


def blamed_the_site_message(blame: str, stop: PhaseStop | None) -> str:
    """Why a reply that asks the user to wait for VEuPathDB is refused.

    The turn's own stop is the cause, so the refusal hands the model that
    sentence to write instead of an external one.
    """
    cause = (
        f"what stopped this turn is that {stop.render()}"
        if stop is not None
        else "no pass of this turn reported a stop"
    )
    return (
        f"Your reply attributes this turn's outcome to VEuPathDB ({blame}), and "
        f"no VEuPathDB call of this turn failed. Rewrite it: {cause}. State "
        f"that, state what happens next, and never ask the user to retry "
        f"because the site is busy."
    )


def unverified_build_message(outcome: BuildOutcome | None) -> str:
    """Why a turn that built something is asked to verify before it answers.

    The check is asked for once. A second answer that still declines is the
    model's to give: only it knows whether a check is possible right now.
    """
    pushed = len(outcome.pushed_step_ids) if outcome is not None else 0
    root = outcome.root_count if outcome is not None else None
    count = "unknown" if root is None else str(root)
    return (
        f"This turn changed the strategy - {pushed} step(s) on VEuPathDB, root "
        f"count {count} - and nothing verified the result. Call verify_strategy, "
        f"or state in your reply why verification is not possible right now."
    )
