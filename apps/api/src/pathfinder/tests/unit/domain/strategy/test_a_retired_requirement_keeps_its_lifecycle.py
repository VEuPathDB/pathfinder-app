"""A requirement the researcher takes back, or that another replaces, leaves the
live record with its lifecycle."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.domain.caveats import RequirementGap, check_gaps
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ReplacedLifecycle,
    WithdrawnLifecycle,
    provisional_constraints,
)
from pathfinder.domain.strategy.requirement_lifecycle import (
    RetiredRequirement,
    reopened,
    restored,
    retire,
    withdrawn_by,
)

_CUTOFF = Constraint(
    kind=ConstraintKind.PERCENTILE,
    requested_value="top 50th percentile",
    label="expression cutoff",
    source=ConstraintSource.USER_EXPLICIT,
)
_SIGNAL = Constraint(
    kind=ConstraintKind.OTHER,
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
    assert [r.lifecycle for r in retired] == [ReplacedLifecycle(by=_QUARTILE.key)]


def test_a_requirement_stated_again_is_live_again() -> None:
    held = [
        RetiredRequirement(
            constraint=_CUTOFF, lifecycle=WithdrawnLifecycle(turn_id="t")
        )
    ]

    assert reopened(held, [_CUTOFF, _SIGNAL]) == []


def test_a_statement_names_the_held_requirement_its_words_carry() -> None:
    kinase = _SIGNAL.model_copy(update={"requested_value": "protein kinase"})
    stated = _SIGNAL.model_copy(update={"requested_value": "the signal peptide"})

    assert withdrawn_by([kinase, _SIGNAL], [stated]) == [_SIGNAL]


def test_a_statement_of_a_single_valued_kind_names_its_one_value() -> None:
    stated = _CUTOFF.model_copy(update={"requested_value": "the expression cutoff"})

    assert withdrawn_by([_CUTOFF, _SIGNAL], [stated]) == [_CUTOFF]


def test_a_statement_names_nothing_the_thread_does_not_hold() -> None:
    stated = _SIGNAL.model_copy(update={"requested_value": "exported"})

    assert withdrawn_by([_SIGNAL], [stated]) == []


def test_a_withdrawn_cutoff_is_no_gap_while_a_live_requirement_still_is() -> None:
    """The toxodb shape: a cutoff stated on one turn, removed on a later one."""
    live, retired = retire([_CUTOFF, _SIGNAL], [], [_CUTOFF], turn_id="t4")
    review = VerificationReview(
        requirements=[
            RequirementCheck(
                text="top 50th percentile expression",
                turn=2,
                how="parameter",
                status="unmet",
            ),
            RequirementCheck(
                text="signal peptide", turn=1, how="search", status="unmet"
            ),
        ]
    )

    gaps = check_gaps(
        structure=None,
        words=[],
        review=review,
        requirements=[*(r.grounded() for r in retired), *provisional_constraints(live)],
    )

    assert gaps == [RequirementGap(text="signal peptide", status="unmet")]


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


def test_only_a_withdrawn_combination_names_the_sides_a_delete_removed() -> None:
    with pytest.raises(ValidationError) as raised:
        RetiredRequirement(
            constraint=_SIGNAL,
            lifecycle=WithdrawnLifecycle(turn_id="turn-4"),
            sides=("signal peptide",),
        )

    assert raised.value.errors()[0]["msg"] == (
        "Value error, only a withdrawn combination names the sides a delete removed"
    )
