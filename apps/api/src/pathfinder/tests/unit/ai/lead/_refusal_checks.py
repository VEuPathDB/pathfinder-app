"""The one thing every refusal owes the thread: nothing of it moved.

A refused pass leaves the committed spec, both baselines and the strategy
exactly as the dispatch found them, and a valid pass afterwards still lands.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.tests.unit.ai.lead._disagreement_drafts import with_the_proteome
from pathfinder.tests.unit.ai.lead._disagreement_facts import (
    StepFacts,
    committed_facts,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    DisagreementThread,
    kept,
)


class ThreadState(BaseModel):
    """Everything a refusal must leave alone."""

    model_config = ConfigDict(frozen=True)

    graph: dict[str, StepFacts]
    spec: OperationalSpec
    before_turn: OperationalSpec


def thread_state(thread: DisagreementThread) -> ThreadState:
    return ThreadState(
        graph=thread.facts(),
        spec=thread.spec.model_copy(deep=True),
        before_turn=thread.before_turn.model_copy(deep=True),
    )


async def a_refusal_that_keeps_the_thread_whole(thread: DisagreementThread) -> str:
    """Refuse the framed pass, then prove a valid one still lands on the same thread."""
    found = thread_state(thread)
    refusal = await thread.edit()
    assert isinstance(refusal, str)
    assert thread_state(thread) == found
    assert thread.before_dispatch == found.spec
    assert thread.committed == []
    thread.frames(with_the_proteome(2), declared=kept(*thread.criteria))
    delta = await thread.edit()
    assert isinstance(delta, EditDelta)
    assert [op.kind for op in committed_facts(thread.committed)] == [
        "addLeaf",
        "addCombine",
    ]
    return refusal
