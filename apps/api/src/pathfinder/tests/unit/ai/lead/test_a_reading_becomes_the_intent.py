from __future__ import annotations

import pytest

from pathfinder.ai.lead.intent import IntentClassification, NamedControls
from pathfinder.ai.lead.message_intent import intent_of
from pathfinder.domain.message_reading import (
    Effect,
    MessageReading,
    StatedCount,
    StatedDataType,
    StatedFoldChange,
    StatedOrganism,
    StatedOrtholog,
    StatedPercentile,
    StatedProperty,
    StatedRecordType,
    StatedRequest,
    StatedSignificance,
    StatedText,
    StatedUntyped,
    StatedWithdrawal,
    Want,
)
from pathfinder.domain.strategy.constraints import (
    ConstraintKind,
    ConstraintSource,
    CountValue,
    DataTypeValue,
    FoldChangeValue,
    OrganismValue,
    OrthologValue,
    PercentileValue,
    PropertyValue,
    RecordTypeValue,
    SignificanceValue,
    TextValue,
    UntypedValue,
)


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


def test_each_requirement_is_a_stated_constraint_of_its_kind() -> None:
    request = StatedRequest(
        goal="3D7 genes with a signal peptide at adjusted p 0.05",
        requirements=[
            StatedOrganism(
                quote="P. falciparum 3D7",
                kind="organism",
                value="Plasmodium falciparum 3D7",
                organism="Plasmodium falciparum 3D7",
            ),
            StatedSignificance(
                quote="adjusted p <= 0.05",
                kind="significance",
                value="adjusted p <= 0.05",
                statistic="adjusted_p",
                at_most=0.05,
            ),
            StatedProperty(
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
            ConstraintKind.PROPERTY,
            "predicted signal peptide",
            "a predicted signal peptide",
            ConstraintSource.USER_EXPLICIT,
            False,
        ),
    ]
    assert intent.inferred_goal == "3D7 genes with a signal peptide at adjusted p 0.05"


def test_each_typed_requirement_carries_its_value_onto_the_constraint() -> None:
    request = StatedRequest(
        requirements=[
            StatedPercentile(
                quote="top 5 percent",
                kind="percentile",
                value="top 5%",
                end="top",
                share=5,
            ),
            StatedFoldChange(
                quote="log2 fold change > 5",
                kind="fold_change",
                value="log2 fold change > 5",
                cut=5,
                scale="log2",
                direction="up",
            ),
            StatedSignificance(
                quote="p-value < 1e-10",
                kind="significance",
                value="p < 1e-10",
                statistic="p_value",
                at_most=1e-10,
            ),
            StatedUntyped(
                quote="from the 2019 study", kind="untyped", value="2019 study"
            ),
            StatedOrganism(
                quote="in 3D7",
                kind="organism",
                value="Plasmodium falciparum 3D7",
                organism="Plasmodium falciparum 3D7",
            ),
            StatedProperty(quote="secreted", kind="property", value="secreted"),
            StatedCount(
                quote="2 to 99 transmembrane domains",
                kind="count",
                value="at least 2 transmembrane domains",
                feature="transmembrane domains",
                op=">=",
                number=2,
            ),
            StatedOrtholog(
                quote="syntenic orthologs in P. vivax P01",
                kind="ortholog",
                value="syntenic orthologs in Plasmodium vivax P01",
                organisms=["Plasmodium vivax P01"],
                syntenic=True,
            ),
            StatedText(
                quote="kinase in the product name",
                kind="text",
                value="kinase in the product name",
                phrase="kinase",
            ),
            StatedDataType(
                quote="microarray experiment",
                kind="data_type",
                value="microarray",
                data="microarray",
            ),
            StatedRecordType(
                quote="their proteins",
                kind="record_type",
                value="proteins",
                record_class="sequence",
                role="through",
            ),
        ]
    )

    intent = intent_of(_reading("new"), request)

    assert [(c.kind, c.value) for c in intent.explicit_constraints] == [
        (ConstraintKind.PERCENTILE, PercentileValue(end="top", share=5)),
        (
            ConstraintKind.FOLD_CHANGE,
            FoldChangeValue(cut=5, scale="log2", direction="up"),
        ),
        (
            ConstraintKind.STATISTICAL_THRESHOLD,
            SignificanceValue(statistic="p_value", at_most=1e-10),
        ),
        (ConstraintKind.UNTYPED, UntypedValue(text="2019 study")),
        (
            ConstraintKind.ORGANISM,
            OrganismValue(organism="Plasmodium falciparum 3D7"),
        ),
        (ConstraintKind.PROPERTY, PropertyValue(phrase="secreted")),
        (
            ConstraintKind.COUNT,
            CountValue(feature="transmembrane domains", op=">=", value=2),
        ),
        (
            ConstraintKind.ORTHOLOG,
            OrthologValue(organisms=["Plasmodium vivax P01"], syntenic=True),
        ),
        (ConstraintKind.TEXT, TextValue(phrase="kinase")),
        (ConstraintKind.DATA_TYPE, DataTypeValue(data="microarray")),
        (
            ConstraintKind.RECORD_TYPE,
            RecordTypeValue(record_class="sequence", role="through"),
        ),
    ]


def test_a_stated_percentile_reads_from_the_extraction_s_json() -> None:
    request = StatedRequest.model_validate(
        {
            "requirements": [
                {
                    "quote": "top 5 percent",
                    "kind": "percentile",
                    "value": "top 5%",
                    "end": "top",
                    "share": 5,
                },
                {"quote": "secreted", "kind": "property", "value": "secreted"},
            ]
        }
    )

    assert [r.typed() for r in request.requirements] == [
        PercentileValue(end="top", share=5),
        PropertyValue(phrase="secreted"),
    ]


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
