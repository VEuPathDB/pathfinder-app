"""A turn writes a strategy memory only when it was asked to change one."""

from __future__ import annotations

import pytest

from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.memory_candidates import collect_memory_candidates
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

_PREFERENCE = (
    "Please remember for future sessions: I always work with P. falciparum 3D7."
)


def _state(classification: IntentClassification | None) -> PipelineState:
    intent = (
        None
        if classification is None
        else UserIntent(
            raw_text=_PREFERENCE,
            classification=classification,
            inferred_goal="store a default organism",
        )
    )
    return pipeline_state(
        user_prompt=_PREFERENCE,
        domain=StrategyDomainState(
            user_intent=intent,
            operational_spec=OperationalSpec(
                goal=_PREFERENCE,
                interpreted_goal=_PREFERENCE,
                criteria=[
                    Criterion(id="c1", text="organism", search_name="GenesByTaxon"),
                ],
            ),
        ),
    )


def _strategy_keys(state: PipelineState) -> list[str]:
    return [
        key
        for value, key in collect_memory_candidates(state)
        if value.kind == "strategy"
    ]


@pytest.mark.parametrize(
    "classification",
    [
        IntentClassification.MEMORY_REQUEST,
        IntentClassification.CONTEXT_STATEMENT,
        IntentClassification.FOLLOW_UP_QUESTION,
        IntentClassification.OFF_TOPIC,
        IntentClassification.DENIAL,
    ],
)
def test_a_turn_that_was_not_asked_to_build_writes_no_strategy_memory(
    classification: IntentClassification,
) -> None:
    assert _strategy_keys(_state(classification)) == []


def test_a_build_turn_still_writes_its_strategy_memory() -> None:
    state = _state(IntentClassification.NEW_STRATEGY)

    assert _strategy_keys(state) == [f"strategy:{state.conversation_id.hex}"]


def test_an_unclassified_turn_still_writes_its_strategy_memory() -> None:
    state = _state(None)

    assert _strategy_keys(state) == [f"strategy:{state.conversation_id.hex}"]
