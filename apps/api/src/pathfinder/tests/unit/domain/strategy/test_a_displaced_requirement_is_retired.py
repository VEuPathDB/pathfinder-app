"""A requirement the record displaces leaves it retired, with the key of the
requirement that took its place, so no path removes one without a record."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.domain.caveats import check_gaps
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
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
_AND = _stated(ConstraintKind.COMBINATION, "signal peptide AND GPI anchor text match")


def test_a_new_combination_retires_the_one_it_displaces() -> None:
    recorded = with_requirements([_ORGANISM, _OR], [_ORGANISM, _AND])

    assert recorded.live == [_ORGANISM, _AND]
    assert recorded.displaced == [
        RetiredRequirement(constraint=_OR, lifecycle=ReplacedLifecycle(by=_AND.key))
    ]


def test_a_restated_requirement_displaces_nothing() -> None:
    recorded = with_requirements([_ORGANISM, _OR], [_ORGANISM])

    assert recorded.live == [_ORGANISM, _OR]
    assert recorded.displaced == []


_PLASMODIUM = _stated(ConstraintKind.ORGANISM, "Plasmodium")
_PF3D7 = _stated(ConstraintKind.ORGANISM, "Plasmodium falciparum 3D7")
_PVIVAX = _stated(ConstraintKind.ORGANISM, "Plasmodium vivax P01")


def test_a_new_value_of_a_held_single_valued_kind_replaces_it() -> None:
    recorded = with_requirements([_PLASMODIUM], [_PF3D7])

    assert (recorded.live, recorded.displaced) == (
        [_PF3D7],
        [
            RetiredRequirement(
                constraint=_PLASMODIUM, lifecycle=ReplacedLifecycle(by=_PF3D7.key)
            )
        ],
    )


def test_two_values_stated_together_both_stand() -> None:
    recorded = with_requirements([], [_PF3D7, _PVIVAX])

    assert (recorded.live, recorded.displaced) == ([_PF3D7, _PVIVAX], [])


def test_a_value_added_as_an_alternative_stands_beside_the_held_one() -> None:
    recorded = with_requirements([_PF3D7], [_PVIVAX], adds_alternatives=True)

    assert (recorded.live, recorded.displaced) == ([_PF3D7, _PVIVAX], [])


def test_a_new_value_of_a_many_valued_kind_adds() -> None:
    kinase = _stated(ConstraintKind.OTHER, "protein kinase")
    signal = _stated(ConstraintKind.OTHER, "signal peptide")

    assert with_requirements([kinase], [signal]).live == [kinase, signal]


def test_the_thread_keeps_the_displaced_combination_retired() -> None:
    domain = StrategyDomainState(requirements=[_ORGANISM, _OR])
    domain.turn_markers.message_id = uuid4()

    domain.record_intent(
        UserIntent(
            classification=IntentClassification.EDIT_STRATEGY,
            inferred_goal="make it AND instead of OR",
            explicit_constraints=[_AND],
        ),
        request_text="make it AND instead of OR",
    )

    assert [c.key for c in domain.requirements] == [_ORGANISM.key, _AND.key]
    assert domain.retired_requirements == [
        RetiredRequirement(constraint=_OR, lifecycle=ReplacedLifecycle(by=_AND.key))
    ]


def test_the_fragments_of_a_displaced_combination_are_no_gaps() -> None:
    domain = StrategyDomainState(requirements=[_ORGANISM, _OR])
    domain.record_requirements([_AND])
    review = VerificationReview(
        requirements=[
            RequirementCheck(
                text=(
                    "Use a text search for GPI anchor in the gene product "
                    "descriptions as the stand-in"
                ),
                turn=2,
                how="search",
                status="unmet",
            ),
            RequirementCheck(
                text="keep it OR with the signal peptide",
                turn=2,
                how="structure",
                status="unmet",
            ),
        ]
    )

    gaps = check_gaps(
        structure=None,
        words=[],
        review=review,
        requirements=[
            *(r.grounded() for r in domain.retired_requirements),
        ],
    )

    assert gaps == []


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
                lifecycle=ReplacedLifecycle(by=_ORGANISM.key),
            )
        ],
    )
