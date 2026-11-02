from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from functools import cache
from typing import get_args

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field
from pydantic_ai import Agent
from pydantic_ai.messages import UserContent
from pydantic_ai.models import Model
from veupathdb_mcp.catalog import (
    Choice,
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionRequest,
    DecisionResponse,
    PredicateQuestion,
    decide,
)

from pathfinder.ai.capabilities.metering import SpendMeter
from pathfinder.ai.prompts.loader import load_reading_guide, load_request_guide
from pathfinder.domain.caveats import EditDirection
from pathfinder.domain.message_reading import (
    Effect,
    MessageReading,
    StatedRequest,
    Want,
)

READING_CONFIDENCE = 0.6
FLAG_PROBABILITY = 0.5
_PURPOSE = "message reading"
_BULLET = re.compile(r"^- `([a-z_]+)`: (.+)$")
_FLAGS = ("disputes_result", "audit", "remember", "context_only", "off_topic")
_EDIT_DIRECTIONS: dict[str, str] = {
    "loosen": "the message asks the result to admit more records: a lower cut, a wider range, a requirement dropped",
    "tighten": "the message asks the result to admit fewer records",
    "other": "any other message",
}

type Decide = Callable[[DecisionRequest], Awaitable[DecisionResponse | None]]


async def decide_reading(request: DecisionRequest) -> DecisionResponse | None:
    return await decide(request, purpose=_PURPOSE)


class ReaderInput(CamelModel):
    model_config = ConfigDict(frozen=True)

    conversation: str
    strategy: str
    steps: list[str] = Field(default_factory=list)
    message: str
    files: list[str] = Field(default_factory=list)
    question_open: bool = False
    held: dict[str, str] = Field(default_factory=dict)


class ReadingGuide(CamelModel):
    model_config = ConfigDict(frozen=True)

    intro: str
    effects: dict[str, str]
    wants: dict[str, str]
    flags: dict[str, str]


@cache
def reading_guide() -> ReadingGuide:
    text = load_reading_guide()
    sections = text.split("\n## ")

    def bullets(head: str) -> dict[str, str]:
        block = next(s for s in sections if s.startswith(head))
        return {
            m.group(1): m.group(2)
            for line in block.splitlines()
            if (m := _BULLET.match(line))
        }

    return ReadingGuide(
        intro=sections[0].strip(),
        effects=bullets("A. effect"),
        wants=bullets("B. wants"),
        flags=bullets("C. flags"),
    )


def _held(read: ReaderInput) -> str:
    listed = "\n".join(f"{number}: {text}" for number, text in read.held.items())
    return f"\n\n## The requirements the conversation holds\n{listed}" if listed else ""


def _context(read: ReaderInput, *, latest_first: bool, held: bool = False) -> str:
    steps = "\n".join(read.steps) or "(no steps)"
    attached = (
        f"\n\n## The files attached to it\n{', '.join(read.files)}"
        if read.files
        else ""
    )
    latest = (
        f"## The researcher's latest message (label this one)\n{read.message}{attached}"
    )
    rest = (
        f"## The strategy now\n{read.strategy}\n\n## Its steps\n{steps}\n\n"
        f"## The conversation so far\n{read.conversation or '(this is the first message of the conversation)'}"
        f"{_held(read) if held else ''}"
    )
    return f"{latest}\n\n{rest}" if latest_first else f"{rest}\n\n{latest}"


def _choices(defined: Mapping[str, str]) -> list[Choice]:
    return [Choice(value=name, description=text) for name, text in defined.items()]


def _request(read: ReaderInput, *, latest_first: bool, flags: bool) -> DecisionRequest:
    guide = reading_guide()
    questions: list[ChoiceQuestion | PredicateQuestion] = [
        ChoiceQuestion(
            name="effect",
            instructions="What the latest message asks to happen to the strategy.",
            choices=_choices(guide.effects),
        ),
        ChoiceQuestion(
            name="wants",
            instructions="What the latest message asks to be told or shown. A message can carry an effect and a want together.",
            choices=_choices(guide.wants),
        ),
        ChoiceQuestion(
            name="edit_direction",
            instructions="Which way a change moves the result.",
            choices=_choices(_EDIT_DIRECTIONS),
        ),
    ]
    if flags:
        questions += [
            PredicateQuestion(name=name, instructions=guide.flags[name])
            for name in _FLAGS
        ]
        if read.question_open:
            questions.append(
                PredicateQuestion(
                    name="answers_open",
                    instructions="The assistant's last reply ended on a question or a card waiting for an answer, and the latest message answers it: it picks an option, says yes or no, or asks for exactly what the question offered.",
                )
            )
    return DecisionRequest(
        input=f"{guide.intro}\n\n{_context(read, latest_first=latest_first)}",
        questions=questions,
    )


def _averaged(first: ChoiceAnswer, second: ChoiceAnswer | None) -> tuple[str, float]:
    if second is None:
        return first.choice, first.confidence
    a = {p.value: p.probability for p in first.probabilities}
    b = {p.value: p.probability for p in second.probabilities}
    summed = {k: a.get(k, 0.0) + b.get(k, 0.0) for k in a.keys() | b.keys()}
    best = max(summed, key=lambda k: summed[k])
    return best, summed[best] / 2


def _effect(value: str) -> Effect:
    return next(e for e in get_args(Effect.__value__) if e == value)


def _want(value: str) -> Want:
    return next(w for w in get_args(Want.__value__) if w == value)


def _direction(value: str) -> EditDirection:
    return next(d for d in get_args(EditDirection.__value__) if d == value)


async def _decisions_reading(read: ReaderInput, ask: Decide) -> MessageReading | None:
    first, second = await asyncio.gather(
        ask(_request(read, latest_first=False, flags=True)),
        ask(_request(read, latest_first=True, flags=False)),
    )
    if first is None:
        return None
    effect_one, wants_one, direction = (
        first.choice(n) for n in ("effect", "wants", "edit_direction")
    )
    if effect_one is None or wants_one is None or direction is None:
        return None
    effect, effect_confidence = _averaged(
        effect_one, None if second is None else second.choice("effect")
    )
    wants, wants_confidence = _averaged(
        wants_one, None if second is None else second.choice("wants")
    )
    flag = {
        name: (
            p.probability >= FLAG_PROBABILITY
            if (p := first.predicate(name)) is not None
            else False
        )
        for name in (*_FLAGS, "answers_open")
    }
    return MessageReading(
        effect=_effect(effect),
        wants=_want(wants),
        answers_open=read.question_open and flag["answers_open"],
        disputes_result=flag["disputes_result"],
        audit=flag["audit"],
        remember=flag["remember"],
        context_only=flag["context_only"],
        off_topic=flag["off_topic"],
        edit_direction=_direction(direction.choice),
        read_by="decisions",
        effect_confidence=effect_confidence,
        wants_confidence=wants_confidence,
    )


class _ModelReading(CamelModel):
    effect: Effect
    wants: Want
    answers_open: bool = False
    disputes_result: bool = False
    audit: bool = False
    remember: bool = False
    context_only: bool = False
    off_topic: bool = False
    edit_direction: EditDirection = "other"


def _prompt(
    read: ReaderInput, files: Sequence[UserContent], *, held: bool = False
) -> list[UserContent]:
    return [_context(read, latest_first=False, held=held), *files]


async def _model_reading(
    read: ReaderInput,
    files: Sequence[UserContent],
    model: Model | str,
    meter: SpendMeter,
    model_id: str,
) -> MessageReading:
    agent: Agent[None, _ModelReading] = Agent(
        model,
        output_type=_ModelReading,
        instructions=load_reading_guide(),
        capabilities=[meter.on(model_id)],
    )
    out = (await agent.run(_prompt(read, files))).output
    return MessageReading(
        **out.model_dump(exclude={"answers_open"}),
        answers_open=read.question_open and out.answers_open,
        read_by="model",
    )


def _quotes_refusal(outside: list[str]) -> str:
    listed = "; ".join(f'"{q}"' for q in outside)
    return f"These quotes are not words of the latest message: {listed}. Copy each quote character for character from it."


async def _stated_request(
    read: ReaderInput,
    files: Sequence[UserContent],
    model: Model | str,
    meter: SpendMeter,
    model_id: str,
) -> StatedRequest:
    agent: Agent[None, StatedRequest] = Agent(
        model,
        output_type=StatedRequest,
        instructions=load_request_guide(),
        capabilities=[meter.on(model_id)],
    )
    prompt = _prompt(read, files, held=True)
    stated = (await agent.run(prompt)).output
    outside = stated.quotes_outside(read.message)
    if outside:
        stated = (await agent.run([*prompt, _quotes_refusal(outside)])).output
    return stated.within(read.message, read.held)


def _settled(reading: MessageReading) -> bool:
    return (
        min(reading.effect_confidence, reading.wants_confidence) >= READING_CONFIDENCE
    )


async def read_message(
    read: ReaderInput,
    *,
    files: Sequence[UserContent] = (),
    model: Model | str,
    model_id: str,
    meter: SpendMeter,
    ask: Decide = decide_reading,
) -> tuple[MessageReading, StatedRequest]:
    modeling = asyncio.create_task(_model_reading(read, files, model, meter, model_id))
    try:
        decided, stated = await asyncio.gather(
            _decisions_reading(read, ask),
            _stated_request(read, files, model, meter, model_id),
        )
        if decided is not None and _settled(decided):
            return decided, stated
        modeled = await modeling
    finally:
        modeling.cancel()
    if decided is None:
        return modeled, stated
    return decided.model_copy(
        update={"effect": modeled.effect, "wants": modeled.wants, "read_by": "model"}
    ), stated


__all__ = ["READING_CONFIDENCE", "ReaderInput", "read_message", "reading_guide"]
