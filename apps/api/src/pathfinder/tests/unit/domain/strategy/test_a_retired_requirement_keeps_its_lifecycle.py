"""A requirement the researcher takes back, or that another replaces, leaves the
live record with its lifecycle."""

from __future__ import annotations

from pathfinder.domain.caveats import RequirementGap, check_gaps
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ReplacedLifecycle,
    WithdrawnLifecycle,
)
from pathfinder.domain.strategy.requirement_lifecycle import (
    RetiredRequirement,
    reopened,
    restored,
    retire,
)

_CUTOFF = Constraint(
    kind=ConstraintKind.PERCENTILE,
    requested_value="top 50th percentile",
    label="expression cutoff",
    source=ConstraintSource.USER_EXPLICIT,
)
_SIGNAL = Constraint(
    kind=ConstraintKind.UNTYPED,
    requested_value="signal peptide",
    label="localisation",
    source=ConstraintSource.USER_EXPLICIT,
)
_QUARTILE = Constraint(
    kind=ConstraintKind.PERCENTILE,
    requested_value="top quartile",
    label="expression cutoff",
    source=ConstraintSource.USER_EXPLICIT,
)


def test_a_withdrawn_requirement_leaves_the_live_record_on_its_turn() -> None:
    live, retired = retire([_CUTOFF, _SIGNAL], [], [_CUTOFF], turn_id="turn-4")

    assert live == [_SIGNAL]
    assert retired == [
        RetiredRequirement(
            constraint=_CUTOFF, lifecycle=WithdrawnLifecycle(turn_id="turn-4")
        )
    ]


def test_a_requirement_retired_beside_a_new_value_of_its_kind_is_replaced() -> None:
    live, retired = retire(
        [_CUTOFF, _QUARTILE], [], [_CUTOFF], turn_id="turn-4", stated=[_QUARTILE]
    )

    assert live == [_QUARTILE]
    assert [r.lifecycle for r in retired] == [ReplacedLifecycle(by=_QUARTILE.id)]


def test_a_requirement_stated_again_is_live_again() -> None:
    held = [
        RetiredRequirement(
            constraint=_CUTOFF, lifecycle=WithdrawnLifecycle(turn_id="t")
        )
    ]

    assert reopened(held, [_CUTOFF, _SIGNAL]) == []


def test_a_withdrawn_cutoff_is_no_gap_while_a_live_requirement_still_is() -> None:
    """The toxodb shape: a cutoff stated on one turn, removed on a later one."""
    live, retired = retire([_CUTOFF, _SIGNAL], [], [_CUTOFF], turn_id="t4")
    gaps = check_gaps(
        words=[],
        unstated=[_CUTOFF, *live],
        retired={r.constraint.id for r in retired},
    )

    assert gaps == [
        RequirementGap(text=_SIGNAL.requested_value, requirement=_SIGNAL.id)
    ]


def test_a_declined_message_takes_back_what_it_retired() -> None:
    retired = [
        RetiredRequirement(
            constraint=_CUTOFF, lifecycle=WithdrawnLifecycle(turn_id="turn-4")
        ),
        RetiredRequirement(
            constraint=_SIGNAL, lifecycle=WithdrawnLifecycle(turn_id="turn-2")
        ),
        RetiredRequirement(
            constraint=_QUARTILE, lifecycle=ReplacedLifecycle(by="percentile:top 5%")
        ),
    ]

    live, kept = restored(retired, turn_id="turn-4", dropped=["percentile:top 5%"])

    assert live == [_CUTOFF, _QUARTILE]
    assert [r.constraint for r in kept] == [_SIGNAL]


def test_a_stored_withdrawn_combination_with_sides_loads_and_shows_no_row() -> None:
    stored = RetiredRequirement.model_validate(
        {
            "constraint": {
                "kind": "combination",
                "requestedValue": "protein kinase domain AND no transmembrane domain",
                "label": "combination",
                "source": "user_explicit",
            },
            "lifecycle": {"state": "withdrawn", "turnId": "turn-4"},
            "sides": ["no transmembrane domain"],
        }
    )

    assert stored.shown_requirements() == []
