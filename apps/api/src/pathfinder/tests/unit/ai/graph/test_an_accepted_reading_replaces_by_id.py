"""An accepted reading replaces the requirements its question names by id, is
recorded from the question that offered it, and its stand-in ends with it."""

from __future__ import annotations

from veupathdb.domain.parameters import StringValue

from pathfinder.ai.graph.thread_requirements import ThreadRequirements
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ReplacedLifecycle,
    WithdrawnLifecycle,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import OpenQuestion, SlotQuestion
from pathfinder.domain.strategy.readings import AcceptedReading, Reading
from pathfinder.tests._support.requirement_values import without_ids

EVERY, SHARE = "PLAS=61T AND TOXO=0T", "PLAS>=55T AND TOXO=0T"
_EXPRESSION = "phyletic_expression"
_SHARE_LABEL = "At least 55 of the 61 genomes (90%)"
_SHARE_CAVEAT = "Keeps groups missing from up to 6 genomes"


def _stated(kind: ConstraintKind, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        label=value,
        source=ConstraintSource.USER_EXPLICIT,
    )


_PRESENT = _stated(ConstraintKind.UNTYPED, "present in all Plasmodium species")
_STAGE = _stated(ConstraintKind.UNTYPED, "expressed in blood stages")
_PLASMODIUM = _stated(ConstraintKind.ORGANISM, "Plasmodium")


def _criterion(criterion_id: str, value: str = SHARE) -> Criterion:
    return Criterion(
        id=criterion_id,
        text="groups in every Plasmodium genome and in no Toxoplasma genome",
        search_name="GroupsByPhyleticPattern",
        resolved_params={
            _EXPRESSION: BoundValue(value=StringValue(value=value), source="card")
        },
    )


def _asked(
    criterion_id: str,
    prompt: str,
    replaces: list[str],
    dimension: ConstraintKind = ConstraintKind.UNTYPED,
) -> OpenQuestion:
    return SlotQuestion(
        question=prompt,
        dimension=dimension,
        criterion_id=criterion_id,
        param_name=_EXPRESSION,
        requirements=["R1"],
        readings=[
            Reading(label="Every one of the 61 genomes", value=EVERY),
            Reading(label=_SHARE_LABEL, value=SHARE, caveat=_SHARE_CAVEAT),
        ],
    ).typed(_criterion(criterion_id), noun="group", replaces=replaces)


def _accepted(replaces: list[str]) -> AcceptedReading:
    return AcceptedReading(
        reading=_SHARE_LABEL,
        caveat=_SHARE_CAVEAT,
        params={_EXPRESSION: SHARE},
        replaces=replaces,
    )


def _stand_in(prompt: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.UNTYPED,
        requested_value=_SHARE_LABEL,
        label=prompt,
        source=ConstraintSource.USER_EXPLICIT,
    )


def _retired(thread: ThreadRequirements) -> list[tuple[str, object]]:
    return [(r.constraint.id, r.lifecycle) for r in thread.retired_requirements]


def test_a_reading_replaces_the_requirement_its_question_names_whatever_the_text() -> (
    None
):
    prompt = "Present in which Plasmodium genomes?"
    thread = ThreadRequirements(
        requirements=[_PRESENT, _STAGE],
        open_questions=[_asked("c_plas", prompt, [_PRESENT.id])],
    )

    spec = thread.accept_reading(
        OperationalSpec(criteria=[_criterion("c_plas")]),
        "c_plas",
        _accepted([_PRESENT.id]),
    )

    stand_in = thread.requirements[-1]
    assert without_ids(thread.requirements) == without_ids([_STAGE, _stand_in(prompt)])
    assert _retired(thread) == [(_PRESENT.id, ReplacedLifecycle(by=stand_in.id))]
    assert spec.criteria[0].accepted_reading == _accepted([_PRESENT.id]).model_copy(
        update={"stand_in": stand_in.id}
    )


def test_a_reading_offered_on_two_criteria_stands_in_from_its_own_question() -> None:
    thread = ThreadRequirements(
        requirements=[_PRESENT],
        open_questions=[
            _asked("c_one", "Present in which genomes of the first list?", []),
            _asked("c_two", "Present in which genomes of the second list?", []),
        ],
    )

    thread.accept_reading(
        OperationalSpec(criteria=[_criterion("c_one"), _criterion("c_two")]),
        "c_two",
        _accepted([]),
    )

    assert without_ids(thread.requirements) == without_ids(
        [_PRESENT, _stand_in("Present in which genomes of the second list?")]
    )


def test_a_reading_on_an_organism_question_stands_in_as_other_and_keeps_the_scope() -> (
    None
):
    prompt = "Which Plasmodium genomes?"
    thread = ThreadRequirements(
        requirements=[_PLASMODIUM, _PRESENT],
        open_questions=[
            _asked(
                "c_plas",
                prompt,
                [_PLASMODIUM.id, _PRESENT.id],
                dimension=ConstraintKind.ORGANISM,
            )
        ],
    )

    thread.accept_reading(
        OperationalSpec(criteria=[_criterion("c_plas")]),
        "c_plas",
        _accepted([_PLASMODIUM.id, _PRESENT.id]),
    )

    assert without_ids(thread.requirements) == without_ids(
        [_PLASMODIUM, _stand_in(prompt)]
    )
    assert [held for held, _ in _retired(thread)] == [_PRESENT.id]


def _held_thread(prompt: str) -> tuple[ThreadRequirements, OperationalSpec]:
    thread = ThreadRequirements(
        requirements=[_PRESENT],
        open_questions=[_asked("c_plas", prompt, [_PRESENT.id])],
    )
    spec = thread.follow_readings(
        OperationalSpec(criteria=[_criterion("c_plas")]),
        OperationalSpec(
            criteria=[
                _criterion("c_plas").model_copy(
                    update={"accepted_reading": _accepted([_PRESENT.id])}
                )
            ]
        ),
    )
    assert spec is not None
    return thread, spec


def test_a_reading_newly_held_is_accepted() -> None:
    prompt = "Present in which Plasmodium genomes?"

    thread, _ = _held_thread(prompt)

    assert without_ids(thread.requirements) == without_ids([_stand_in(prompt)])


def test_the_stand_in_ends_with_its_reading() -> None:
    prompt = "Present in which Plasmodium genomes?"
    thread, held = _held_thread(prompt)
    [stand_in] = thread.requirements
    moved = held.model_copy(
        update={
            "criteria": [
                held.criteria[0].model_copy(
                    update={
                        "resolved_params": {
                            _EXPRESSION: BoundValue(
                                value=StringValue(value=EVERY), source="card"
                            )
                        }
                    }
                )
            ]
        }
    )

    thread.follow_readings(held, moved)

    assert thread.requirements == []
    assert _retired(thread) == [
        (_PRESENT.id, ReplacedLifecycle(by=stand_in.id)),
        (stand_in.id, WithdrawnLifecycle(turn_id="")),
    ]


def test_a_reading_still_held_changes_nothing() -> None:
    prompt = "Present in which Plasmodium genomes?"
    thread, held = _held_thread(prompt)

    assert thread.follow_readings(held, held) == held
    assert without_ids(thread.requirements) == without_ids([_stand_in(prompt)])
