"""The typed intent the Lead classifies a turn into."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from veupathdb.domain.strategy.constraints import ConstraintKind

from pathfinder.ai.lead.intent import IntentClassification, UserIntent


def test_user_intent_default_non_differential() -> None:
    intent = UserIntent(
        raw_text="hello",
        classification=IntentClassification.OFF_TOPIC,
        inferred_goal="say hi",
    )
    assert intent.is_differential is False
    assert intent.differential_sides == []
    assert intent.referenced_step_ids == []


def test_user_intent_differential_sides_two_items() -> None:
    intent = UserIntent(
        raw_text="X vs Y",
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="diff",
        is_differential=True,
        differential_sides=["X", "Y"],
    )
    assert intent.differential_sides == ["X", "Y"]


def test_user_intent_differential_sides_rejects_three() -> None:
    with pytest.raises(ValidationError):
        UserIntent(
            raw_text="X vs Y vs Z",
            classification=IntentClassification.NEW_STRATEGY,
            inferred_goal="diff",
            is_differential=True,
            differential_sides=["X", "Y", "Z"],
        )


def test_the_constraint_kinds_the_classifier_reads_come_from_the_enum() -> None:
    """A new ConstraintKind reaches the classifier without a hand edit."""
    description = UserIntent.model_fields["explicit_constraints"].description or ""

    missing = [kind.value for kind in ConstraintKind if kind.value not in description]

    assert missing == []
