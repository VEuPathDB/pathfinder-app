"""The researcher's words of this turn, read before the Lead runs into the intent
the turn is held to."""

from __future__ import annotations

from pydantic_ai.messages import BinaryContent, UserContent
from pydantic_ai.ui.vercel_ai.request_types import FileUIPart

from pathfinder.ai.capabilities.metering import SpendMeter
from pathfinder.ai.graph._lead_capture import LeadRunCapture, absorb_outside_spend
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.held_intent import hold_the_intent
from pathfinder.ai.lead.intent import UserIntent
from pathfinder.ai.lead.message_intent import intent_of
from pathfinder.ai.lead.message_reader import ReaderInput, read_message
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.models.mock.reading import scripted_intent
from pathfinder.domain.exchanges import exchanges_text
from pathfinder.domain.strategy.requirement_reports import numbered_requirements
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.platform.model_keys import is_mock_deployment, keyed_model
from pathfinder.services.strategies.record_classes import record_class_names


def _words(state: PipelineState, *, new_message: bool) -> str | None:
    if new_message:
        return state.user_prompt or None
    notes = [
        answer.note
        for answers in state.user_question_answers.values()
        for answer in answers
        if answer.note
    ]
    return "\n".join(notes) or None


def _strategy(graph: StrategyGraph | None) -> tuple[str, list[str]]:
    if graph is None or not graph.steps:
        return "(no strategy yet)", []
    steps = [
        f"{step.id}: {step.display_label}"
        + (
            f" ({step.operator.value} of {', '.join(step.input_ids())})"
            if step.operator is not None
            else ""
        )
        for step in graph.steps.values()
    ]
    return f"{graph.name}: {len(steps)} steps", steps


def _files(state: PipelineState) -> list[UserContent]:
    content = state.user_content
    return (
        []
        if isinstance(content, str)
        else [part for part in content if isinstance(part, BinaryContent)]
    )


def _reader_input(
    state: PipelineState,
    deps: LeadDeps,
    words: str,
    record_classes: dict[str, str],
) -> ReaderInput:
    strategy, steps = _strategy(deps.runtime.strategy_session.get_graph(None))
    markers = deps.state.turn_markers
    return ReaderInput(
        conversation=exchanges_text(deps.state.domain.exchanges),
        strategy=strategy,
        steps=steps,
        message=words,
        files=[
            part.filename or part.media_type
            for part in state.user_parts
            if isinstance(part, FileUIPart)
        ],
        question_open=bool(markers.questions_at_arrival)
        or state.pending_approval is not None,
        held={
            number: f"{c.kind.value}: {c.requested_value}"
            for number, c in numbered_requirements(
                deps.state.domain.requirements
            ).items()
        },
        record_classes=record_classes,
    )


async def _intent_of_words(
    state: PipelineState,
    deps: LeadDeps,
    words: str,
    *,
    new_message: bool,
    model_id: str,
    meter: SpendMeter,
) -> UserIntent:
    if is_mock_deployment():
        return scripted_intent(deps.state, words)
    reading, request = await read_message(
        _reader_input(
            state, deps, words, await record_class_names(deps.runtime.site_id)
        ),
        files=_files(state) if new_message else [],
        model=keyed_model(model_id),
        model_id=model_id,
        meter=meter,
    )
    return intent_of(reading, request)


async def read_the_words(
    state: PipelineState,
    deps: LeadDeps,
    *,
    new_message: bool,
    model_id: str,
    capture: LeadRunCapture,
) -> None:
    words = _words(state, new_message=new_message)
    if words is None:
        return
    meter = SpendMeter()
    try:
        intent = await _intent_of_words(
            state, deps, words, new_message=new_message, model_id=model_id, meter=meter
        )
    finally:
        for spend in meter.spent:
            absorb_outside_spend(capture, spend.tokens, spend.cost_usd, spend.paid_by)
    await hold_the_intent(deps, intent, words)


async def classify_the_words(
    state: PipelineState, deps: LeadDeps, *, model_id: str, meter: SpendMeter
) -> None:
    words = _words(state, new_message=True)
    if words is None:
        return
    deps.intent = await _intent_of_words(
        state, deps, words, new_message=True, model_id=model_id, meter=meter
    )
    state.turn_markers.intent_classified = True


__all__ = ["read_the_words"]
