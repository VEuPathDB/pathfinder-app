"""The transcript's facts and assumed sections: every field the facts part holds,
as the product shows it, and the two assumed counts under their own names."""

from __future__ import annotations

from pathfinder.devtools.models import LedgerConstraintsProbe
from pathfinder.domain.strategy.operational_spec import ValueSource
from pathfinder.domain.turn_facts import ParameterFact, SourceFact, StepFact, TurnFacts

# The words the facts part shows beside a value for who set it.
SOURCE_LABELS: dict[ValueSource, str] = {
    "stated": "stated",
    "chosen": "chosen",
    "default": "site default",
    "card": "your answer",
    "held": "in the strategy",
}


def _parameter_lines(fact: ParameterFact) -> list[str]:
    shown = f"{fact.value} ({fact.label})" if fact.label else fact.value
    return [
        f"  {fact.display_name}: {shown} ({SOURCE_LABELS[fact.source]})",
        *(f"    {note}" for note in fact.notes),
    ]


def _step_lines(step: StepFact, noun: str, sources: list[SourceFact]) -> list[str]:
    title, *reason = step.model_copy(update={"parameters": [], "error": ""}).lines(noun)
    return [
        title,
        *(f"  {line}" for line in reason),
        *(line for fact in step.parameters for line in _parameter_lines(fact)),
        *([f"  {step.error}"] if step.error else []),
        *(f"  {s.line()}" for s in sources if s.step_id == step.step_id),
    ]


def facts_lines(facts: TurnFacts) -> list[str]:
    """The facts part line by line, each value with who set it. A record read
    from a step the facts part does not hold is named as not shown."""
    step_ids = {step.step_id for step in facts.steps}
    step_sources = [s for s in facts.sources if s.step_id]
    rest = facts.model_copy(
        update={"steps": [], "sources": [s for s in facts.sources if not s.step_id]}
    ).lines()
    return [
        "Plan" if facts.draft else "Strategy",
        *(
            line
            for step in facts.steps
            for line in _step_lines(step, facts.record_noun, step_sources)
        ),
        *rest,
        *(
            f"not shown, its step is not in the facts: {s.line()}"
            for s in step_sources
            if s.step_id not in step_ids
        ),
    ]


def assumed_lines(
    unshown: int | None, constraints: LedgerConstraintsProbe | None
) -> list[str]:
    """``summary.assumed``, the checkpoint's narrowing values the facts part does
    not show, and apart from it the ledger rows the Lead marked assumed."""
    counted = "not counted (no checkpoint read)" if unshown is None else str(unshown)
    rows = [
        g
        for g in (constraints.grounded if constraints is not None else [])
        if g.constraint.source == "assumed"
    ]
    return [
        (
            "summary.assumed (narrowing values no message states that the facts "
            f"part does not show): {counted}"
        ),
        (
            "ledger constraint rows the Lead marked source=assumed "
            f"(not counted in summary.assumed): {len(rows)}"
        ),
        *(
            f"- {g.constraint.label} ({g.constraint.kind}): "
            f"{g.constraint.requested_value!r} -> {g.status}"
            for g in rows
        ),
    ]
