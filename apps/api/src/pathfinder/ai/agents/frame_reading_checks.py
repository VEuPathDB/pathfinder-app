"""The readings a FRAME question offers, held to what the site builds: a value
the site validates, on a parameter no vocabulary offers, approximating
requirements the pass was given."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_ai import DeferredToolRequests, ModelRetry, RunContext
from veupathdb.domain.parameters import ParamKind
from veupathdb.errors import ValidationError

from pathfinder.ai.agents.refusal_bound import may_refuse
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.domain.strategy.readings import Reading, reading_problems
from pathfinder.domain.strategy.requirement_reports import stated_numbers
from pathfinder.services.strategies.reading_check import site_spelling
from pathfinder.services.strategies.record_classes import search_record_types

_TEXT: ParamKind = "string"
_READINGS_ON_A_CARD = 2
_READABLE_KINDS: frozenset[ParamKind] = frozenset(
    {"string", "number", "number-range", "date", "date-range", "timestamp"}
)


async def _record_type(ctx: RunContext[AgentDeps], criterion: Criterion) -> str | None:
    if criterion.record_class is not None:
        return criterion.record_class
    listed = await search_record_types(ctx.deps.site_id, [criterion.search_name])
    return listed.get(criterion.search_name)


def _kind(criterion: Criterion, param: str) -> ParamKind:
    held = criterion.resolved_params.get(param)
    if held is not None:
        return held.value.type
    kinds: dict[str, ParamKind] = {
        s.param_name: s.param_kind for s in criterion.open_params
    }
    return kinds.get(param, _TEXT)


@dataclass(frozen=True)
class _Held:
    question: SlotQuestion
    problems: list[str] = field(default_factory=list)
    gaps: list[PassGap] = field(default_factory=list)


def _named(question: SlotQuestion) -> str:
    if question.names_a_slot:
        return f"{question.criterion_id}.{question.param_name}"
    return f"the question {question.question!r}"


def _first_sentence(text: str) -> str:
    return text.partition(". ")[0].rstrip(".")


def _key_problems(question: SlotQuestion, held: list[str], named: str) -> list[str]:
    if not held:
        return []
    if not question.requirements:
        missing = (
            f"{named}: name in the question's `requirements` the keys of the "
            f"requirements its readings approximate, from {', '.join(held)}"
        )
        return [missing]
    unknown = sorted(set(question.requirements) - set(held))
    if not unknown:
        return []
    replaced = (
        f"{named}: replace {unknown} in the question's `requirements` with keys "
        f"the requirement list holds, from {', '.join(held)}"
    )
    return [replaced]


def _unkeyed(question: SlotQuestion, held: list[str]) -> list[PassGap]:
    if not held or set(question.requirements) & set(held):
        return []
    said = (
        f"{question.question!r} names no stated requirement, so a pick of its "
        f"readings replaces none."
    )
    return [PassGap(kind="readings_name_no_requirement", sentence=said)]


def _bare(question: SlotQuestion, problems: list[str]) -> _Held:
    said = (
        f"{question.question!r} reaches the card with no readings: "
        f"{'; '.join(problems)}."
    )
    return _Held(
        question.model_copy(update={"readings": []}),
        problems,
        [PassGap(kind="question_without_readings", sentence=said)],
    )


def _unknown_class(question: SlotQuestion, criterion: Criterion) -> PassGap:
    said = (
        f"The record type of {criterion.search_name} is not known, so the site did "
        f"not check the readings of {_named(question)}."
    )
    return PassGap(kind="record_type_unknown", sentence=said)


async def _spelled(
    ctx: RunContext[AgentDeps],
    question: SlotQuestion,
    criterion: Criterion,
    record_type: str,
) -> tuple[list[Reading], list[str]]:
    named = _named(question)
    readings: list[Reading] = []
    refusals: list[str] = []
    for reading in question.readings:
        try:
            spelled = await site_spelling(
                ctx.deps.site_id,
                record_type,
                criterion,
                question.param_name,
                reading.value,
            )
        except ValidationError as refused:
            refusals.append(
                f"the site refuses {reading.label!r} on {named}: "
                f"{_first_sentence(str(refused))}"
            )
            continue
        readings.append(
            reading
            if spelled is None
            else reading.model_copy(update={"value": spelled})
        )
    return readings, refusals


def _unreadable(question: SlotQuestion, criterion: Criterion) -> str:
    named = _named(question)
    kind = _kind(criterion, question.param_name)
    if kind not in _READABLE_KINDS:
        return (
            f"{named} takes {kind}, and only a free-text or range parameter "
            f"takes readings"
        )
    if any(s.param_name != question.param_name for s in criterion.open_params):
        return f"{named}: bind the rest of {criterion.id} before its readings"
    return ""


async def _checked(ctx: RunContext[AgentDeps], question: SlotQuestion) -> _Held:
    state = ctx.deps.agent_state
    named = _named(question)
    shaped = reading_problems(
        question.readings, options=question.options, names_a_slot=question.names_a_slot
    )
    if shaped:
        offered = [r.label for r in question.readings]
        return _bare(
            question,
            [f"{named} offers the readings {offered}: {'; '.join(shaped)}"],
        )
    held = stated_numbers(state.stated_requirements)
    keys = _key_problems(question, held, named)
    criterion = next(
        (
            c
            for c in state.operational_spec_draft.criteria
            if c.id == question.criterion_id
        ),
        None,
    )
    if criterion is None:
        return _Held(question, keys, _unkeyed(question, held))
    unreadable = _unreadable(question, criterion)
    if unreadable:
        return _bare(question, [unreadable])
    record_type = await _record_type(ctx, criterion)
    readings, refusals = (
        (list(question.readings), [])
        if record_type is None
        else await _spelled(ctx, question, criterion, record_type)
    )
    if len(readings) < _READINGS_ON_A_CARD:
        return _bare(question, refusals)
    kept = question.model_copy(update={"readings": readings})
    shaped = reading_problems(
        kept.readings, options=kept.options, names_a_slot=kept.names_a_slot
    )
    if shaped:
        return _bare(question, [f"{named}: {'; '.join(shaped)}"])
    return _Held(
        kept,
        [*keys, *refusals],
        [
            *(
                PassGap(kind="reading_left_out", sentence=f"The card leaves out {r}.")
                for r in refusals
            ),
            *_unkeyed(kept, held),
            *([] if record_type else [_unknown_class(question, criterion)]),
        ],
    )


async def hold_the_readings_to_the_site(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    if not isinstance(output, FrameResult):
        return output
    held = [
        await _checked(ctx, q) if q.readings else _Held(q)
        for q in output.open_questions
    ]
    problems = [p for h in held for p in h.problems]
    state = ctx.deps.agent_state
    if problems and may_refuse(ctx, state.refusals):
        state.refusals += 1
        msg = (
            f"Change these readings, or ask nothing about them and say why in "
            f"summary: {'; '.join(problems)}."
        )
        raise ModelRetry(msg)
    checked = output.model_copy(update={"open_questions": [h.question for h in held]})
    return checked.with_gaps([g for h in held for g in h.gaps])
