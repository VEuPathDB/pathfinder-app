from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue

from strategist.domain.requirement_checks import grounded_check
from strategist.domain.strategy.constraint_grounding import ground_against_spec
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintStatus,
    CountOp,
    CountValue,
    GroundedConstraint,
    OrthologValue,
    PropertyValue,
    RequirementValue,
    TextValue,
    UntypedValue,
    is_blocking,
)
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    RequirementLink,
)
from strategist.tests.unit.domain.strategy._linked_values import linked, requirement

_TM = "GenesByTransmembraneDomains"
_TEXT = "GenesByText"
_ORTHOLOGS = "GenesByOrthologs"
_PV = "Plasmodium vivax P01"
_TG = "Toxoplasma gondii ME49"


def _grounded(held: Constraint, *criteria: Criterion) -> GroundedConstraint:
    [grounded] = ground_against_spec(
        [held], OperationalSpec(goal="g", criteria=list(criteria))
    )
    return grounded


def _count(op: CountOp, value: float) -> Constraint:
    return requirement(
        ConstraintKind.COUNT,
        CountValue(feature="transmembrane domains", op=op, value=value),
    )


def _sized(held: Constraint, count: int | None) -> Criterion:
    return Criterion(
        id="c_sized",
        text="the result",
        search_name=_TM,
        resolved_params={},
        result_count=count,
        answers=[RequirementLink(requirement=held.id, result_size=True)],
    )


@pytest.mark.parametrize(("op", "value"), [(">=", 2), (">", 1), ("=", 2)])
def test_a_count_the_linked_parameter_holds_is_grounded(
    op: CountOp, value: float
) -> None:
    held = _count(op, value)

    grounded = _grounded(held, linked(held, {"min_tm": "2"}, "min_tm", search=_TM))

    assert (grounded.status, grounded.realized_param, grounded.realized_value) == (
        ConstraintStatus.GROUNDED,
        "min_tm",
        "2",
    )
    assert grounded_check(grounded).status == "pass"


def test_a_count_the_parameter_holds_another_way_fails_its_check() -> None:
    held = _count(">=", 2)

    grounded = _grounded(held, linked(held, {"min_tm": "3"}, "min_tm", search=_TM))

    assert (grounded.status, grounded.note, grounded_check(grounded).status) == (
        ConstraintStatus.SUBSTITUTED,
        "asked transmembrane domains >= 2, min_tm holds 3",
        "fail",
    )


def test_a_count_of_the_result_is_compared_with_the_step_s_count() -> None:
    held = _count(">=", 50)

    met = _grounded(held, _sized(held, 120))
    short = _grounded(held, _sized(held, 30))

    assert (met.status, met.realized_value) == (ConstraintStatus.GROUNDED, "120")
    assert (short.status, short.note) == (
        ConstraintStatus.SUBSTITUTED,
        "asked transmembrane domains >= 50, the step returns 30",
    )


def test_a_link_to_the_result_and_a_parameter_at_once_is_refused() -> None:
    with pytest.raises(ValueError, match="result size"):
        RequirementLink(requirement="r", param="min_tm", result_size=True)


def test_an_unlinked_count_is_not_verified_and_never_blocks() -> None:
    grounded = _grounded(_count(">=", 2), linked(_count("<=", 9), {}, search=_TM))

    check = grounded_check(grounded)
    assert (grounded.status, grounded.unverified) == (
        ConstraintStatus.NOT_VERIFIED,
        "no_value_to_compare",
    )
    assert (check.status, check.why_unchecked) == ("unchecked", "no_value_to_compare")
    assert not is_blocking(grounded)


def _transform(held: Constraint, *targets: str) -> Criterion:
    return Criterion(
        id="c_orthologs",
        text="their orthologs",
        search_name=_ORTHOLOGS,
        role="transform",
        organism_param="organism",
        resolved_params={
            "organism": BoundValue(
                value=MultiPickValue(values=list(targets)), source="stated"
            )
        },
        answers=[RequirementLink(requirement=held.id)],
    )


def _orthologs(*organisms: str) -> Constraint:
    return requirement(
        ConstraintKind.ORTHOLOG, OrthologValue(organisms=list(organisms))
    )


def test_the_organisms_the_linked_transform_targets_ground_the_ortholog() -> None:
    held = _orthologs(_PV)

    grounded = _grounded(held, _transform(held, _PV))

    assert (grounded.status, grounded.realized_value) == (
        ConstraintStatus.GROUNDED,
        _PV,
    )


def test_a_transform_to_another_organism_fails_the_ortholog() -> None:
    held = _orthologs(_PV)

    grounded = _grounded(held, _transform(held, _TG))

    assert (grounded.status, grounded.note) == (
        ConstraintStatus.SUBSTITUTED,
        f"asked orthologs in {_PV}, the transform targets {_TG}",
    )


def test_an_ortholog_no_criterion_links_is_not_verified() -> None:
    grounded = _grounded(_orthologs(_PV), _transform(_count(">=", 1), _PV))

    assert (grounded.status, grounded.unverified) == (
        ConstraintStatus.NOT_VERIFIED,
        "no_step_states_it",
    )


def _text(phrase: str, *, exact: bool, bound: str) -> GroundedConstraint:
    held = requirement(ConstraintKind.TEXT, TextValue(phrase=phrase, exact=exact))
    return _grounded(
        held, linked(held, {"text_expression": bound}, "text_expression", search=_TEXT)
    )


@pytest.mark.parametrize(
    ("phrase", "exact", "bound"),
    [
        ("cysteine-rich protein", True, '"Cysteine-rich protein"'),
        ("kinase", False, "protein kinase*"),
        ("surface antigen", False, "variant erythrocyte surface antigen"),
    ],
)
def test_a_phrase_the_linked_parameter_holds_grounds_the_text(
    phrase: str, exact: bool, bound: str
) -> None:
    grounded = _text(phrase, exact=exact, bound=bound)

    assert (grounded.status, grounded.realized_value) == (
        ConstraintStatus.GROUNDED,
        bound,
    )


@pytest.mark.parametrize(
    ("phrase", "exact", "bound"),
    [
        ("cysteine-rich protein", True, "cysteine-rich protein kinase"),
        ("surface antigen", False, "variant erythrocyte antigen"),
    ],
)
def test_a_phrase_the_parameter_does_not_hold_fails_the_text(
    phrase: str, exact: bool, bound: str
) -> None:
    grounded = _text(phrase, exact=exact, bound=bound)

    assert grounded.status is ConstraintStatus.SUBSTITUTED
    assert grounded_check(grounded).status == "fail"


def test_a_text_linked_with_no_parameter_has_no_value_to_compare() -> None:
    held = requirement(ConstraintKind.TEXT, TextValue(phrase="kinase"))

    grounded = _grounded(
        held, linked(held, {"text_expression": "kinase"}, None, search=_TEXT)
    )

    assert (grounded.status, grounded.unverified) == (
        ConstraintStatus.NOT_VERIFIED,
        "no_value_to_compare",
    )


def test_a_linked_property_is_answered_by_its_step() -> None:
    held = requirement(ConstraintKind.PROPERTY, PropertyValue(phrase="secreted"))
    criterion = linked(held, {}, None, search="GenesWithSignalPeptide").model_copy(
        update={"search_display_name": "Signal Peptide Prediction"}
    )

    grounded = _grounded(held, criterion)

    check = grounded_check(grounded)
    assert (grounded.status, grounded.realized_value) == (
        ConstraintStatus.GROUNDED,
        "Signal Peptide Prediction",
    )
    assert (check.status, check.evidence) == (
        "pass",
        "answered by step 'Signal Peptide Prediction'",
    )


def test_an_unlinked_property_is_not_verified() -> None:
    held = requirement(ConstraintKind.PROPERTY, PropertyValue(phrase="secreted"))

    grounded = _grounded(held, linked(_count(">=", 1), {}, search=_TM))

    check = grounded_check(grounded)
    assert (check.status, check.why_unchecked) == ("unchecked", "no_step_states_it")


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (ConstraintKind.UNTYPED, UntypedValue(text="from the 2019 study")),
        (ConstraintKind.COUNT, None),
        (ConstraintKind.PROPERTY, None),
    ],
)
def test_a_requirement_with_no_typed_value_is_not_verified(
    kind: ConstraintKind, value: RequirementValue | None
) -> None:
    held = requirement(kind, value)

    grounded = _grounded(held, linked(held, {"min_tm": "2"}, "min_tm", search=_TM))

    check = grounded_check(grounded)
    assert (grounded.status, check.status, check.why_unchecked) == (
        ConstraintStatus.NOT_VERIFIED,
        "unchecked",
        "untyped",
    )
    assert not is_blocking(grounded)


def test_a_not_verified_grounding_names_why() -> None:
    held = _count(">=", 2)

    with pytest.raises(ValueError, match="not verified"):
        GroundedConstraint(constraint=held, status=ConstraintStatus.NOT_VERIFIED)
