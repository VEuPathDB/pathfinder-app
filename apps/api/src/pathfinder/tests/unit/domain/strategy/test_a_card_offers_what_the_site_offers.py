"""A card over a vocabulary slot offers the site's values, and a question about
a requirement no search states offers to drop it or keep it."""

from __future__ import annotations

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import Criterion, OpenSlot
from pathfinder.domain.strategy.questions import (
    Keep,
    OpenQuestion,
    SetValues,
    SlotQuestion,
    Withdraw,
    with_withdrawals,
)

_REGION = Criterion(
    id="c_sex_region",
    text="Culex quinquefasciatus JHB genes that fall within the sex-determining region",
    search_name="GenesByLocation",
    open_params=[
        OpenSlot(
            criterion_id="c_sex_region",
            param_name="chromosomeOptional",
            param_kind="single-pick-vocabulary",
            options=["1", "2", "3"],
        )
    ],
)


def test_a_card_over_a_vocabulary_slot_offers_every_value_of_the_site() -> None:
    """The vectorbase location card: the site offers chromosomes 1, 2 and 3."""
    asked = SlotQuestion(
        question=(
            "Which genomic location defines the Culex quinquefasciatus JHB "
            "sex-determining region?"
        ),
        criterion_id="c_sex_region",
        param_name="chromosomeOptional",
        options=["1", "Provide start and end coordinates"],
    ).typed(_REGION, noun="gene")

    assert [o.binding for o in asked.options] == [
        SetValues(criterion_id="c_sex_region", params={"chromosomeOptional": value})
        for value in ("1", "2", "3")
    ]


_GPI = Constraint(
    kind=ConstraintKind.COMBINATION,
    requested_value="predicted GPI anchor OR signal peptide",
    label="evidence combination",
    source=ConstraintSource.USER_EXPLICIT,
)


def test_a_question_about_an_unstated_requirement_offers_drop_and_keep() -> None:
    """The piroplasmadb pass: its one question is about the GPI anchor."""
    frames = OpenQuestion(
        question=(
            "No catalog search on this site states predicted GPI-anchor genes for "
            "Cytauxzoon felis Winnie. Should I proceed with the available "
            "signal-peptide search alone, or should you specify an alternative "
            "evidence type?"
        ),
        dimension=ConstraintKind.DATA_TYPE,
    )

    [asked] = with_withdrawals([frames], [_GPI])

    assert asked.question == frames.question
    assert [o.binding for o in asked.options] == [
        Withdraw(constraint_id=_GPI.key),
        Keep(constraint_id=_GPI.key),
    ]
