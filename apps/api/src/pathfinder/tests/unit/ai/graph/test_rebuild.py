"""The saved state is rebuilt at the turn's entry, or the turn refuses plainly."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from pathfinder.ai.graph.rebuild import rebuilt_state
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.platform.errors import ConversationFromEarlierBuildError


def _outcome_mapping() -> dict[str, object]:
    return {
        "pushed_step_ids": ["step_a"],
        "failed_steps": [],
        "skipped_step_ids": [],
        "wdk_strategy_id": 330642473,
        "wdk_url": None,
        "counts": {"step_a": 87},
        "root_count": 87,
        "zero_step_ids": [],
        "node_results": [],
    }


def _constructed_without_validation(outcome: object) -> PipelineState:
    """The checkpoint serializer's fallback: the state built without validation."""
    stored: dict[str, Any] = {"last_build_outcome": outcome}
    return PipelineState.model_construct(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        domain=StrategyDomainState.model_construct(**stored),
    )


def test_a_record_left_as_a_mapping_is_rebuilt_as_its_model() -> None:
    state = rebuilt_state(_constructed_without_validation(_outcome_mapping()))
    assert isinstance(state.domain.last_build_outcome, BuildOutcome)
    assert state.domain.last_build_outcome.root_count == 87


def test_a_value_this_build_cannot_read_ends_the_turn_with_a_sentence() -> None:
    with pytest.raises(ConversationFromEarlierBuildError) as caught:
        rebuilt_state(_constructed_without_validation(5))
    assert "saved by an earlier version of PathFinder" in str(caught.value.detail)
    assert "last_build_outcome" in str(caught.value.detail)
