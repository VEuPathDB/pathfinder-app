from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from strategist.ai.lead.deltas import FrameResult, PassGap
from strategist.domain.refusal import Problem, RefusalKey
from strategist.domain.strategy.questions import SlotQuestion


@dataclass(frozen=True)
class HeldAnswer:
    problem: Problem
    let_through: Callable[[FrameResult], FrameResult]


def held(
    key: RefusalKey, sentence: str, let_through: Callable[[FrameResult], FrameResult]
) -> HeldAnswer:
    return HeldAnswer(
        problem=Problem(key=key, sentence=sentence), let_through=let_through
    )


def gapped(gap: PassGap) -> Callable[[FrameResult], FrameResult]:
    return lambda output: output.with_gaps([gap])


def _same(one: SlotQuestion, other: SlotQuestion) -> bool:
    return (one.criterion_id, one.param_name, one.question) == (
        other.criterion_id,
        other.param_name,
        other.question,
    )


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


__all__ = ["HeldAnswer", "gapped", "held", "with_question", "without_question"]
