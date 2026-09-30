"""A binding whose count did not arrive takes the count its built step holds,
so its values read at that count and never as not measured."""

from __future__ import annotations

from veupathdb.domain.parameters import StringValue

from pathfinder.domain.strategy.measurement_clauses import counted_clauses
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
)
from pathfinder.domain.value_caveats import assumed_value_caveats

_STEP = "step_ortholog_agam"


def _unread() -> OperationalSpec:
    """The vectorbase ortholog bind whose count did not arrive in its budget."""
    return OperationalSpec(
        criteria=[
            Criterion(
                id=_STEP,
                text="an ortholog in Anopheles gambiae PEST",
                search_name="GenesByOrthologPattern",
                resolved_params={
                    "included_species": BoundValue(
                        value=StringValue(value="agam"), source="chosen"
                    )
                },
                param_display_names={"included_species": "Included Species"},
                measurements=[
                    Measurement(
                        kind="bound_count", param="included_species", reading="agam"
                    )
                ],
            )
        ]
    )


def test_the_unread_bind_says_its_effect_was_not_measured() -> None:
    assert [c.sentence for c in assumed_value_caveats(_unread())] == [
        (
            "Included Species is agam, chosen: its effect was not measured, since "
            "the count of the search at agam did not arrive"
        )
    ]


def test_the_steps_count_replaces_a_bind_count_that_did_not_arrive() -> None:
    live = _unread().counted_at({_STEP: 12318})
    [criterion] = live.criteria

    assert (
        criterion.result_count,
        counted_clauses(criterion, "included_species", noun="gene"),
        assumed_value_caveats(live),
    ) == (
        12318,
        [
            (
                "Included Species at the chosen agam: 12,318 genes; its other "
                "readings: not measured"
            )
        ],
        [],
    )


def test_a_step_with_no_count_leaves_the_bind_unread() -> None:
    live = _unread().counted_at({_STEP: None, "step_other": 5})

    assert live == _unread()


def test_a_bind_that_counted_keeps_its_own_count() -> None:
    counted = _unread().model_copy(deep=True)
    counted.criteria[0].result_count = 12000

    assert counted.counted_at({_STEP: 12318}).criteria[0].result_count == 12000
