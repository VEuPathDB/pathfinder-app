from __future__ import annotations

import pytest

from pathfinder.ai.lead.intent import IntentClassification, NamedControls
from pathfinder.ai.lead.message_intent import intent_of
from pathfinder.domain.message_reading import (
    Effect,
    MessageReading,
    StatedRequest,
    StatedRequirement,
    StatedWithdrawal,
    Want,
)
from pathfinder.domain.strategy.constraints import ConstraintKind, ConstraintSource


def _reading(
    effect: Effect = "none", wants: Want = "nothing", **flags: bool
) -> MessageReading:
    return MessageReading(effect=effect, wants=wants, read_by="script").model_copy(
        update=flags
    )


@pytest.mark.parametrize(
    ("effect", "classification"),
    [
        ("new", IntentClassification.NEW_STRATEGY),
        ("add", IntentClassification.EXTEND_STRATEGY),
        ("change", IntentClassification.EDIT_STRATEGY),
        ("remove", IntentClassification.EDIT_STRATEGY),
        ("undo", IntentClassification.EDIT_STRATEGY),
    ],
)
def test_an_effect_is_a_building_classification(
    effect: Effect, classification: IntentClassification
) -> None:
    intent = intent_of(_reading(effect), StatedRequest())

    assert (intent.classification, intent.asks_a_change, intent.undo) == (
        classification,
        True,
        effect == "undo",
    )


@pytest.mark.parametrize(
    ("flag", "classification"),
    [
        ("audit", IntentClassification.GENE_MODEL_AUDIT),
        ("remember", IntentClassification.MEMORY_REQUEST),
        ("context_only", IntentClassification.CONTEXT_STATEMENT),
        ("off_topic", IntentClassification.OFF_TOPIC),
        ("answers_open", IntentClassification.CLARIFICATION_RESPONSE),
    ],
)
def test_a_flag_names_the_classification_before_the_effect(
    flag: str, classification: IntentClassification
) -> None:
    intent = intent_of(_reading("add", "status", **{flag: True}), StatedRequest())

    assert intent.classification is classification


def test_an_audit_flag_comes_before_every_other_flag() -> None:
    reading = _reading(audit=True, remember=True, off_topic=True, answers_open=True)

    assert (
        intent_of(reading, StatedRequest()).classification
        is IntentClassification.GENE_MODEL_AUDIT
    )


def test_a_question_that_changes_nothing_is_a_follow_up() -> None:
    intent = intent_of(_reading("none", "status"), StatedRequest())

    assert (intent.classification, intent.asks_a_change) == (
        IntentClassification.FOLLOW_UP_QUESTION,
        False,
    )


def test_a_withdrawal_on_a_question_is_a_change() -> None:
    request = StatedRequest(
        withdrawn=[StatedWithdrawal(quote="drop the fold change", requirement="R2")]
    )

    intent = intent_of(_reading("none", "status"), request)

    assert (intent.classification, intent.asks_a_change, intent.withdrawn_ids) == (
        IntentClassification.EDIT_STRATEGY,
        True,
        [],
    )


def test_a_comparison_carries_its_sides() -> None:
    request = StatedRequest(differential_sides=["3D7", "Dd2"])

    intent = intent_of(_reading("none", "compare"), request)

    assert (intent.is_differential, intent.differential_sides) == (True, ["3D7", "Dd2"])


def test_each_requirement_is_a_stated_constraint_of_the_old_kind() -> None:
    request = StatedRequest(
        goal="3D7 genes with a signal peptide at adjusted p 0.05",
        requirements=[
            StatedRequirement(
                quote="P. falciparum 3D7",
                kind="organism",
                value="Plasmodium falciparum 3D7",
            ),
            StatedRequirement(
                quote="adjusted p <= 0.05",
                kind="significance",
                value="adjusted p <= 0.05",
            ),
            StatedRequirement(
                quote="a predicted signal peptide",
                kind="property",
                value="predicted signal peptide",
                hard=False,
            ),
        ],
    )

    intent = intent_of(_reading("new"), request)

    assert [
        (c.kind, c.requested_value, c.quote, c.source, c.hard)
        for c in intent.explicit_constraints
    ] == [
        (
            ConstraintKind.ORGANISM,
            "Plasmodium falciparum 3D7",
            "P. falciparum 3D7",
            ConstraintSource.USER_EXPLICIT,
            True,
        ),
        (
            ConstraintKind.STATISTICAL_THRESHOLD,
            "adjusted p <= 0.05",
            "adjusted p <= 0.05",
            ConstraintSource.USER_EXPLICIT,
            True,
        ),
        (
            ConstraintKind.OTHER,
            "predicted signal peptide",
            "a predicted signal peptide",
            ConstraintSource.USER_EXPLICIT,
            False,
        ),
    ]
    assert intent.inferred_goal == "3D7 genes with a signal peptide at adjusted p 0.05"


def test_the_named_ids_and_controls_carry_over() -> None:
    request = StatedRequest(
        asks=["how many are left"],
        referenced_step_ids=["step_1"],
        named_gene_ids=["PF3D7_1133400"],
        positive_control_ids=["PF3D7_0304600"],
        negative_control_ids=["PF3D7_0930300"],
    )

    intent = intent_of(_reading("none", "status"), request)

    assert (
        intent.asks,
        intent.referenced_step_ids,
        intent.named_gene_ids,
        intent.named_controls,
    ) == (
        ["how many are left"],
        ["step_1"],
        ["PF3D7_1133400"],
        NamedControls(positive_ids=["PF3D7_0304600"], negative_ids=["PF3D7_0930300"]),
    )


def test_a_message_with_no_controls_names_none() -> None:
    intent = intent_of(_reading("new"), StatedRequest())

    assert (intent.classification, intent.named_controls) == (
        IntentClassification.NEW_STRATEGY,
        None,
    )


def test_the_intent_keeps_the_reading_and_the_request() -> None:
    reading, request = _reading("add", "status"), StatedRequest(goal="add a filter")

    intent = intent_of(reading, request)

    assert (intent.reading, intent.request) == (reading, request)
