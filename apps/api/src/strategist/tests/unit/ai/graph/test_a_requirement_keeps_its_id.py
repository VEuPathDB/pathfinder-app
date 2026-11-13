from __future__ import annotations

from uuid import uuid4

from strategist.ai.graph.thread_requirements import ThreadRequirements
from strategist.ai.graph.turn_records import TurnMarkers
from strategist.ai.lead.intent import IntentClassification, UserIntent
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ReplacedLifecycle,
)


def _stated(kind: ConstraintKind, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        label=value,
        source=ConstraintSource.USER_EXPLICIT,
        quote=value,
    )


def _intent(*constraints: Constraint) -> UserIntent:
    return UserIntent(
        classification=IntentClassification.EDIT_STRATEGY,
        inferred_goal="g",
        explicit_constraints=list(constraints),
    )


def _thread(*held: Constraint) -> ThreadRequirements:
    return ThreadRequirements(
        turn_markers=TurnMarkers(message_id=uuid4()), requirements=list(held)
    )


def test_two_requirements_never_share_an_id() -> None:
    first = _stated(ConstraintKind.UNTYPED, "signal peptide")
    second = _stated(ConstraintKind.UNTYPED, "signal peptide")

    assert first.id != second.id


def test_a_restated_requirement_keeps_the_id_the_thread_holds() -> None:
    held = _stated(ConstraintKind.UNTYPED, "signal peptide")
    thread = _thread(held)

    thread.record(
        _intent(_stated(ConstraintKind.UNTYPED, "signal peptide")),
        ["Only those with a signal peptide."],
    )

    assert [c.id for c in thread.requirements] == [held.id]


def test_a_replacement_names_its_successor_by_id() -> None:
    genus = _stated(ConstraintKind.ORGANISM, "Plasmodium")
    strain = _stated(ConstraintKind.ORGANISM, "Plasmodium falciparum 3D7")
    thread = _thread(genus)

    thread.record(_intent(strain), ["Make that Plasmodium falciparum 3D7."])

    [retired] = thread.retired_requirements
    assert (retired.constraint.id, retired.lifecycle) == (
        genus.id,
        ReplacedLifecycle(by=strain.id),
    )


def test_an_id_a_held_requirement_owns_is_never_taken_by_another() -> None:
    held = _stated(ConstraintKind.UNTYPED, "signal peptide")
    taken = _stated(ConstraintKind.ORGANISM, "Plasmodium falciparum 3D7").model_copy(
        update={"id": held.id}
    )
    thread = _thread(held)

    thread.record(_intent(taken), ["Plasmodium falciparum 3D7 only."])

    assert len({c.id for c in thread.requirements}) == 2


def test_the_classifier_never_writes_an_id() -> None:
    schema = UserIntent.model_json_schema()

    assert "id" not in schema["$defs"]["Constraint"]["properties"]
