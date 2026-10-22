"""The counts of the readings a FRAME question offers, and the site's check of
a reading a card picks."""

from __future__ import annotations

import asyncio

from assistant_core.graph.turn_state import UserQuestionAnswer
from veupathdb.errors import ValidationError

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.card_answers import option_value
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    Measurement,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.services.strategies.measurements import MEASUREMENT_BUDGET_SECONDS
from pathfinder.services.strategies.reading_check import site_spelling


async def _counted(
    deps: LeadDeps, spec: OperationalSpec, question: SlotQuestion
) -> tuple[str, list[Measurement]]:
    criterion = next((c for c in spec.criteria if c.id == question.criterion_id), None)
    if criterion is None or not _countable(criterion, question.param_name):
        return question.criterion_id, []
    record_type = criterion.record_class
    if record_type is None:
        return question.criterion_id, []
    counts = await asyncio.gather(
        *(
            deps.turn_counts.count(
                deps.site_id,
                record_type,
                criterion.search_name,
                {
                    **criterion.param_values,
                    question.param_name: option_value(
                        criterion, question.param_name, reading.value
                    ),
                },
                timeout_seconds=MEASUREMENT_BUDGET_SECONDS,
            )
            for reading in question.readings
        )
    )
    return criterion.id, [
        Measurement(kind="reading", param=question.param_name, reading=r.value, count=n)
        for r, n in zip(question.readings, counts, strict=True)
        if n is not None
    ]


def _countable(criterion: Criterion, param: str) -> bool:
    return (
        bool(criterion.search_name)
        and criterion.role != "transform"
        and all(slot.param_name == param for slot in criterion.open_params)
    )


def _with_counts(criterion: Criterion, counted: list[Measurement]) -> Criterion:
    if not counted:
        return criterion
    replaced = {(m.param, m.reading) for m in counted}
    kept = [
        m
        for m in criterion.measurements
        if m.kind != "reading" or (m.param, m.reading) not in replaced
    ]
    return criterion.model_copy(update={"measurements": [*kept, *counted]})


async def count_readings(deps: LeadDeps, result: FrameResult) -> None:
    domain = deps.state.domain
    spec = domain.operational_spec
    asked = [q for q in result.open_questions if q.readings]
    if spec is None or not asked:
        return
    counted: dict[str, list[Measurement]] = {}
    for criterion_id, measured in await asyncio.gather(
        *(_counted(deps, spec, q) for q in asked)
    ):
        counted.setdefault(criterion_id, []).extend(measured)
    domain.operational_spec = spec.model_copy(
        update={
            "criteria": [_with_counts(c, counted.get(c.id, [])) for c in spec.criteria]
        }
    )


async def refused_picks(
    state: PipelineState, answers: list[UserQuestionAnswer]
) -> dict[str, str]:
    domain = state.domain
    spec = domain.operational_spec
    recorded = {q.question: q for q in domain.open_questions}
    criteria = {} if spec is None else {c.id: c for c in spec.criteria}
    refused: dict[str, str] = {}
    for answer in answers:
        question = recorded.get(answer.prompt)
        for option in [] if question is None else question.options:
            read = option.offered_reading()
            if read is None or option.label not in answer.chosen_labels:
                continue
            criterion = criteria.get(read.criterion_id)
            if criterion is None or criterion.record_class is None:
                continue
            record_type = criterion.record_class
            for param, wire in read.params.items():
                try:
                    await site_spelling(
                        state.site_id, record_type, criterion, param, wire
                    )
                except ValidationError as refusal:
                    refused[option.label] = str(refusal)
    return refused
