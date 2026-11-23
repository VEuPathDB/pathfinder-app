from __future__ import annotations

from collections.abc import Sequence
from functools import reduce

from strategist.ai.agents.held_answer import HeldAnswer
from strategist.ai.lead.deltas import FrameResult
from strategist.domain.refusal import KeyUse, RefusalKey, RefusalLedger


def said(held: Sequence[HeldAnswer]) -> list[str]:
    return [answer.problem.sentence for answer in held]


def let_through(held: Sequence[HeldAnswer], output: FrameResult) -> FrameResult:
    final = reduce(lambda kept, answer: answer.let_through(kept), held, output)
    return final.with_gaps([gap for answer in held for gap in answer.gaps(final)])


def charged(ledger: RefusalLedger) -> list[str]:
    return [use.key.check for use in ledger.uses]


def refused_once(*checks: str) -> RefusalLedger:
    return RefusalLedger(
        uses=tuple(KeyUse(key=RefusalKey(check=check), used=1) for check in checks)
    )
