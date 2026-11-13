from __future__ import annotations

from strategist.ai.lead.intent import IntentClassification, NamedControls, UserIntent
from strategist.domain.message_reading import (
    Effect,
    MessageReading,
    RequirementKind,
    StatedRequest,
    StatedRequirement,
)
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)

_KIND: dict[RequirementKind, ConstraintKind] = {
    "organism": ConstraintKind.ORGANISM,
    "record_type": ConstraintKind.RECORD_TYPE,
    "data_type": ConstraintKind.DATA_TYPE,
    "percentile": ConstraintKind.PERCENTILE,
    "fold_change": ConstraintKind.FOLD_CHANGE,
    "significance": ConstraintKind.STATISTICAL_THRESHOLD,
    "count": ConstraintKind.COUNT,
    "ortholog": ConstraintKind.ORTHOLOG,
    "text": ConstraintKind.TEXT,
    "property": ConstraintKind.PROPERTY,
    "untyped": ConstraintKind.UNTYPED,
}

_BY_EFFECT: dict[Effect, IntentClassification] = {
    "none": IntentClassification.FOLLOW_UP_QUESTION,
    "new": IntentClassification.NEW_STRATEGY,
    "add": IntentClassification.EXTEND_STRATEGY,
    "change": IntentClassification.EDIT_STRATEGY,
    "remove": IntentClassification.EDIT_STRATEGY,
    "undo": IntentClassification.EDIT_STRATEGY,
}


def _effect(reading: MessageReading, request: StatedRequest) -> Effect:
    return (
        "remove" if reading.effect == "none" and request.withdrawn else reading.effect
    )


def _classification(reading: MessageReading, effect: Effect) -> IntentClassification:
    flagged = [
        (reading.audit, IntentClassification.GENE_MODEL_AUDIT),
        (reading.remember, IntentClassification.MEMORY_REQUEST),
        (reading.context_only, IntentClassification.CONTEXT_STATEMENT),
        (reading.off_topic, IntentClassification.OFF_TOPIC),
        (reading.answers_open, IntentClassification.CLARIFICATION_RESPONSE),
    ]
    return next((label for on, label in flagged if on), _BY_EFFECT[effect])


def _constraint(stated: StatedRequirement) -> Constraint:
    return Constraint(
        kind=_KIND[stated.kind],
        requested_value=stated.value,
        label=stated.value,
        source=ConstraintSource.USER_EXPLICIT,
        quote=stated.quote,
        hard=stated.hard,
        value=stated.typed(),
    )


def _controls(request: StatedRequest) -> NamedControls | None:
    if not (request.positive_control_ids or request.negative_control_ids):
        return None
    return NamedControls(
        positive_ids=request.positive_control_ids,
        negative_ids=request.negative_control_ids,
    )


def intent_of(reading: MessageReading, request: StatedRequest) -> UserIntent:
    effect = _effect(reading, request)
    return UserIntent(
        classification=_classification(reading, effect),
        inferred_goal=request.goal,
        is_differential=reading.wants == "compare",
        differential_sides=request.differential_sides,
        edit_direction=reading.edit_direction,
        asks_a_change=effect != "none",
        undo=effect == "undo",
        asks=request.asks,
        referenced_step_ids=request.referenced_step_ids,
        explicit_constraints=[_constraint(r) for r in request.requirements],
        named_controls=_controls(request),
        named_gene_ids=request.named_gene_ids,
        reading=reading,
        request=request,
    )


__all__ = ["intent_of"]
