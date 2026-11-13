from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue

from strategist.domain.strategy.constraint_grounding import ground_against_spec
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    OrganismValue,
)
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)

PF = "Plasmodium falciparum 3D7"


def _organism(words: str, entry: str | None) -> Constraint:
    return Constraint(
        kind=ConstraintKind.ORGANISM,
        requested_value=words,
        label="organism",
        source=ConstraintSource.USER_EXPLICIT,
        value=None if entry is None else OrganismValue(organism=entry),
    )


def _spec(selected: str) -> OperationalSpec:
    return OperationalSpec(
        criteria=[
            Criterion(
                id="c_signal",
                text="with a signal peptide",
                search_name="GenesWithSignalPeptide",
                organism_param="organism",
                resolved_params={
                    "organism": BoundValue(
                        value=MultiPickValue(values=[selected]), source="stated"
                    )
                },
            )
        ]
    )


def test_the_entry_a_criterion_selects_grounds_the_organism() -> None:
    [grounded] = ground_against_spec([_organism("P. falciparum 3D7", PF)], _spec(PF))

    assert (grounded.status, grounded.realized_value, grounded.realized_param) == (
        ConstraintStatus.GROUNDED,
        PF,
        "organism",
    )


def test_another_entry_realizes_nothing_for_the_check_to_count() -> None:
    held = _organism("HB3", "Plasmodium falciparum HB3")

    [grounded] = ground_against_spec([held], _spec(PF))

    assert (grounded.status, grounded.realized_value) == (
        ConstraintStatus.GROUNDED,
        None,
    )


def test_an_organism_with_no_entry_realizes_nothing() -> None:
    [grounded] = ground_against_spec([_organism(PF, None)], _spec(PF))

    assert (grounded.status, grounded.realized_value) == (
        ConstraintStatus.GROUNDED,
        None,
    )
