from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from strategist.ai.lead.deltas import FrameResult, PassGap
from strategist.domain.refusal import Problem, RefusalKey
from strategist.domain.strategy.questions import SlotQuestion

type Changed = Callable[[FrameResult], FrameResult]
type Gaps = Callable[[FrameResult], list[PassGap]]


def kept(output: FrameResult) -> FrameResult:
    return output


@dataclass(frozen=True)
class HeldAnswer:
    problem: Problem
    gaps: Gaps
    let_through: Changed = kept


def held(
    key: RefusalKey, sentence: str, gaps: Gaps, let_through: Changed = kept
) -> HeldAnswer:
    return HeldAnswer(
        problem=Problem(key=key, sentence=sentence), gaps=gaps, let_through=let_through
    )


def gapped(*gaps: PassGap) -> Gaps:
    return lambda final: list(gaps)


def asked_gaps(question: SlotQuestion, *gaps: PassGap) -> Gaps:
    return lambda final: list(gaps) if holds_question(final, question) else []


def _same(one: SlotQuestion, other: SlotQuestion) -> bool:
    return (one.criterion_id, one.param_name, one.question) == (
        other.criterion_id,
        other.param_name,
        other.question,
    )


def holds_question(output: FrameResult, question: SlotQuestion) -> bool:
    return any(_same(q, question) for q in output.open_questions)


def without_question(output: FrameResult, question: SlotQuestion) -> FrameResult:
    kept = [q for q in output.open_questions if not _same(q, question)]
    return output.model_copy(update={"open_questions": kept})


def with_question(
    output: FrameResult, question: SlotQuestion, **update: object
) -> FrameResult:
    changed = [
        q.model_copy(update=update) if _same(q, question) else q
        for q in output.open_questions
    ]
    return output.model_copy(update={"open_questions": changed})


__all__ = [
    "Changed",
    "Gaps",
    "HeldAnswer",
    "asked_gaps",
    "gapped",
    "held",
    "holds_question",
    "kept",
    "with_question",
    "without_question",
]
