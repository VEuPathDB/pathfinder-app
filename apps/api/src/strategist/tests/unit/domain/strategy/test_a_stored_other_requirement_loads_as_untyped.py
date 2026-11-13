from __future__ import annotations

from pydantic import TypeAdapter

from strategist.domain.site_checks import SiteCheck
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    PropertyValue,
    StoredConstraint,
    UntypedValue,
    merge_constraints,
)
from strategist.domain.strategy.questions import OpenQuestion


def test_a_stored_other_requirement_loads_as_untyped_with_its_text() -> None:
    stored = {
        "id": "abc",
        "kind": "other",
        "requested_value": "from the 2019 study",
        "label": "study",
    }

    loaded = TypeAdapter(StoredConstraint).validate_python(stored)

    assert (loaded.kind, loaded.value) == (
        ConstraintKind.UNTYPED,
        UntypedValue(text="from the 2019 study"),
    )


def test_a_stored_other_check_and_question_load_as_untyped() -> None:
    check = SiteCheck.model_validate(
        {
            "kind": "other",
            "subject": "s",
            "status": "unchecked",
            "evidence": "e",
            "why_unchecked": "no_check",
        }
    )
    question = OpenQuestion.model_validate({"question": "q", "dimension": "other"})

    assert (check.kind, question.dimension) == (
        ConstraintKind.UNTYPED,
        ConstraintKind.UNTYPED,
    )


def _property(phrase: str, source: ConstraintSource) -> Constraint:
    return Constraint(
        kind=ConstraintKind.PROPERTY,
        requested_value=phrase,
        label=phrase,
        source=source,
        value=PropertyValue(phrase=phrase),
    )


def test_two_properties_of_one_phrase_are_one_requirement() -> None:
    merged = merge_constraints(
        [_property("secreted", ConstraintSource.ASSUMED)],
        [_property("secreted", ConstraintSource.USER_EXPLICIT)],
    )

    assert [(c.requested_value, c.source) for c in merged] == [
        ("secreted", ConstraintSource.USER_EXPLICIT)
    ]


def test_two_properties_of_other_phrases_both_survive_the_merge() -> None:
    merged = merge_constraints(
        [_property("transmembrane domain", ConstraintSource.ASSUMED)],
        [_property("a transmembrane domain", ConstraintSource.USER_EXPLICIT)],
    )

    assert [c.requested_value for c in merged] == [
        "transmembrane domain",
        "a transmembrane domain",
    ]
