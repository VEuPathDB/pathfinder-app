"""A requirement the record displaces leaves it retired, with the key of the
requirement that took its place, so no path removes one without a record."""

from __future__ import annotations

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ReplacedLifecycle,
)
from pathfinder.domain.strategy.requirement_lifecycle import RetiredRequirement
from pathfinder.domain.strategy.stated_requirements import with_requirements


def _stated(kind: ConstraintKind, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        label=kind.value,
        source=ConstraintSource.USER_EXPLICIT,
    )


_ORGANISM = _stated(ConstraintKind.ORGANISM, "Cytauxzoon felis Winnie")
_OR = _stated(
    ConstraintKind.COMBINATION,
    "Use a text search for GPI anchor in the gene product descriptions as the "
    "stand-in and keep it OR with the signal peptide",
)
_GPI = _stated(ConstraintKind.UNTYPED, "GPI anchor")


def test_a_held_combination_is_displaced_by_no_new_requirement() -> None:
    recorded = with_requirements([_ORGANISM, _OR], [_ORGANISM, _GPI])

    assert recorded == ([_ORGANISM, _OR, _GPI], [])


_PLASMODIUM = _stated(ConstraintKind.ORGANISM, "Plasmodium")
_PF3D7 = _stated(ConstraintKind.ORGANISM, "Plasmodium falciparum 3D7")
_PVIVAX = _stated(ConstraintKind.ORGANISM, "Plasmodium vivax P01")


def test_a_new_value_of_a_held_single_valued_kind_replaces_it() -> None:
    recorded = with_requirements([_PLASMODIUM], [_PF3D7])

    assert (recorded.live, recorded.displaced) == (
        [_PF3D7],
        [
            RetiredRequirement(
                constraint=_PLASMODIUM, lifecycle=ReplacedLifecycle(by=_PF3D7.id)
            )
        ],
    )


def test_two_values_stated_together_both_stand() -> None:
    recorded = with_requirements([], [_PF3D7, _PVIVAX])

    assert (recorded.live, recorded.displaced) == ([_PF3D7, _PVIVAX], [])


def test_a_value_stated_beside_a_held_one_stands_beside_it() -> None:
    beside = _PVIVAX.model_copy(update={"beside": _PF3D7.id})

    recorded = with_requirements([_PF3D7], [beside])

    assert (recorded.live, recorded.displaced) == ([_PF3D7, beside], [])


def test_a_value_stated_beside_another_requirement_still_replaces_its_kind() -> None:
    beside = _PVIVAX.model_copy(update={"beside": "some_other_id"})

    recorded = with_requirements([_PF3D7], [beside])

    assert recorded.live == [beside]


def test_a_new_value_of_a_many_valued_kind_adds() -> None:
    kinase = _stated(ConstraintKind.UNTYPED, "protein kinase")
    signal = _stated(ConstraintKind.UNTYPED, "signal peptide")

    assert with_requirements([kinase], [signal]).live == [kinase, signal]


_ASSUMED_ORGANISM = Constraint(
    kind=ConstraintKind.ORGANISM,
    requested_value="Theileria parva Muguga",
    label="organism",
    source=ConstraintSource.ASSUMED,
)


def test_an_assumed_value_never_displaces_a_stated_one() -> None:
    recorded = with_requirements([_ORGANISM], [_ASSUMED_ORGANISM])

    assert recorded == ([_ORGANISM], [])


def test_a_stated_value_displaces_an_assumed_one() -> None:
    recorded = with_requirements([_ASSUMED_ORGANISM], [_ORGANISM])

    assert recorded == (
        [_ORGANISM],
        [
            RetiredRequirement(
                constraint=_ASSUMED_ORGANISM,
                lifecycle=ReplacedLifecycle(by=_ORGANISM.id),
            )
        ],
    )
