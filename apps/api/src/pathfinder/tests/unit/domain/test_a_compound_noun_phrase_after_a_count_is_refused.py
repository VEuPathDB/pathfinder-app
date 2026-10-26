from __future__ import annotations

import pytest

from pathfinder.domain.reply_references import ProseFault, prose_faults, render_reply
from pathfinder.domain.turn_facts import StepFact, TurnFacts

_GROUPS = TurnFacts(
    record_noun="group",
    steps=[
        StepFact(
            step_id="step_pattern",
            display_name="Phyletic Pattern",
            count=2,
            record_noun="group",
        )
    ],
    root_count=2,
)


@pytest.mark.parametrize("reference", ["[root]", "[count:step_pattern]"])
def test_a_compound_modifier_and_the_noun_after_a_count_are_refused(
    reference: str,
) -> None:
    prose = (
        f"The strategy identifies {reference} single-copy ortholog groups shared "
        "across the full Apicomplexa scope."
    )

    assert prose_faults(prose, _GROUPS) == [
        ProseFault(
            token=f"{reference} single-copy ortholog groups",
            kind="noun_after_count",
            references=(reference,),
        )
    ]


@pytest.mark.parametrize("reference", ["[root]", "[count:step_pattern]"])
def test_a_count_followed_by_its_clause_stands(reference: str) -> None:
    prose = (
        f"The strategy identifies {reference} shared across the full Apicomplexa scope."
    )

    assert prose_faults(prose, _GROUPS) == []
    assert render_reply(prose, _GROUPS) == (
        "The strategy identifies 2 groups shared across the full Apicomplexa scope."
    )


@pytest.mark.parametrize(
    "prose",
    [
        "The strategy keeps [root] cross-checked against the reference groups.",
        "The strategy keeps [root] single-copy in every genome of the groups.",
    ],
)
def test_a_compound_modifier_with_no_noun_right_after_it_stands(prose: str) -> None:
    assert prose_faults(prose, _GROUPS) == []
