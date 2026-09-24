"""What the Lead is told when a build cannot run: a strategy it would replace,
a spec not ready to build, or a structure that is not a WDK tree."""

from __future__ import annotations

from pathfinder.domain.strategy.operational_spec import OperationalSpec

__all__ = [
    "build_not_ready_message",
    "build_would_replace_the_strategy",
    "structure_does_not_convert_message",
]


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


def structure_does_not_convert_message(detail: str) -> str:
    """Why a bound spec whose structure is not a WDK tree is refused.

    Readiness says every criterion is bound. Only the conversion knows whether
    the shape over them is a tree VEuPathDB can hold.
    """
    return (
        f"The plan is bound and its structure does not convert into a WDK "
        f"tree: {detail}. Nothing was built and the strategy is unchanged. "
        f"Call set_structure with a tree whose every combine names an operator "
        f"and joins two inputs."
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
    unbound = [c.id for c in spec.criteria if not c.bound and not c.pending_analysis]
    if unbound:
        return (
            f"These criteria are not bound to a WDK search: {', '.join(unbound)}. "
            "Call frame_problem to bind them."
        )
    open_params = [
        f"{c.id}.{slot.param_name}" for c in spec.criteria for slot in c.open_params
    ]
    if not open_params:
        calls = ", ".join(
            f'create_eda_step(criterion_id="{c.id}")'
            for c in spec.criteria
            if c.pending_analysis
        )
        return (
            f"Every criterion waits for the analysis workflow, so build_strategy "
            f"has no search to mint. Run the EDA route pinned for each and call "
            f"{calls}; the first export becomes the strategy."
        )
    return (
        f"These criteria still need user-supplied parameters: "
        f"{', '.join(open_params)}. Ask the user for them, then build."
    )
