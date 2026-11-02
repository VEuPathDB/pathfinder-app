"""The typed intent the Lead classifies a turn into."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.ai.lead.intent import (
    IntentClassification,
    UserIntent,
)
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.tests._support.requirement_values import without_ids


def test_user_intent_default_non_differential() -> None:
    intent = UserIntent(
        classification=IntentClassification.OFF_TOPIC,
        inferred_goal="say hi",
    )
    assert intent.is_differential is False
    assert intent.differential_sides == []
    assert intent.referenced_step_ids == []


def test_user_intent_differential_sides_two_items() -> None:
    intent = UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="diff",
        is_differential=True,
        differential_sides=["X", "Y"],
    )
    assert intent.differential_sides == ["X", "Y"]


def test_user_intent_differential_sides_rejects_three() -> None:
    with pytest.raises(ValidationError):
        UserIntent(
            classification=IntentClassification.NEW_STRATEGY,
            inferred_goal="diff",
            is_differential=True,
            differential_sides=["X", "Y", "Z"],
        )


def _organism(value: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.ORGANISM, requested_value=value, label="organism"
    )


def test_a_comparison_keeps_every_requirement_the_reading_states() -> None:
    intent = UserIntent(
        classification=IntentClassification.FOLLOW_UP_QUESTION,
        inferred_goal="compare the count in the two strains",
        is_differential=True,
        differential_sides=[
            "Trypanosoma brucei gambiense DAL972",
            "Trypanosoma brucei brucei TREU927",
        ],
        explicit_constraints=[_organism("Trypanosoma brucei brucei TREU927")],
    )

    assert without_ids(intent.explicit_constraints) == without_ids(
        [_organism("Trypanosoma brucei brucei TREU927")]
    )


def test_the_intent_names_no_strategy_id() -> None:
    """A strategy id the model writes is checked by nothing, so it is not held."""
    assert "referenced_strategy_ids" not in UserIntent.model_fields
