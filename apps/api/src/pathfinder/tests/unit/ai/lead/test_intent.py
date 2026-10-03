"""The typed intent the Lead classifies a turn into."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.domain.question_rows import ResearcherAsk
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind


def test_user_intent_default_non_differential() -> None:
    intent = UserIntent(
        classification=IntentClassification.OFF_TOPIC,
        inferred_goal="say hi",
    )
    assert intent.is_differential is False
    assert intent.differential_sides == []
    assert intent.referenced_step_ids == []


def test_user_intent_differential_sides_two_items() -> None:
    intent = UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="diff",
        is_differential=True,
        differential_sides=["X", "Y"],
    )
    assert intent.differential_sides == ["X", "Y"]


def test_user_intent_differential_sides_rejects_three() -> None:
    with pytest.raises(ValidationError):
        UserIntent(
            classification=IntentClassification.NEW_STRATEGY,
            inferred_goal="diff",
            is_differential=True,
            differential_sides=["X", "Y", "Z"],
        )


def test_the_constraint_kinds_the_classifier_reads_come_from_the_enum() -> None:
    """A new ConstraintKind reaches the classifier without a hand edit."""
    description = UserIntent.model_fields["explicit_constraints"].description or ""

    missing = [kind.value for kind in ConstraintKind if kind.value not in description]

    assert missing == []


def _organism(value: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.ORGANISM, requested_value=value, label="organism"
    )


def test_the_sides_of_a_comparison_are_no_constraints() -> None:
    """The microsporidiadb comparison of a name search with a domain search."""
    intent = UserIntent(
        classification=IntentClassification.FOLLOW_UP_QUESTION,
        inferred_goal="compare the name search with the domain searches",
        is_differential=True,
        differential_sides=[
            "polar tube protein name search",
            "InterPro or Pfam polar tube protein domain search",
        ],
        explicit_constraints=[
            _organism("Enterocytozoon bieneusi H348"),
            Constraint(
                kind=ConstraintKind.OTHER,
                requested_value="polar tube protein family",
                label="domain family",
            ),
            Constraint(
                kind=ConstraintKind.COMBINATION,
                requested_value="InterPro OR Pfam",
                label="domain search alternatives",
                hard=False,
            ),
        ],
    )

    assert intent.explicit_constraints == [_organism("Enterocytozoon bieneusi H348")]


def test_a_compared_strain_is_no_organism_requirement() -> None:
    """The tritrypdb comparison of one count across two strains."""
    intent = UserIntent(
        classification=IntentClassification.FOLLOW_UP_QUESTION,
        inferred_goal="compare the count in the two strains",
        is_differential=True,
        differential_sides=[
            "Trypanosoma brucei gambiense DAL972",
            "Trypanosoma brucei brucei TREU927",
        ],
        explicit_constraints=[_organism("Trypanosoma brucei brucei TREU927")],
    )

    assert intent.explicit_constraints == []


def test_a_constraint_of_a_request_that_compares_nothing_stays() -> None:
    intent = UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="find the polar tube proteins",
        differential_sides=["polar tube protein name search"],
        explicit_constraints=[_organism("Enterocytozoon bieneusi H348")],
    )

    assert intent.explicit_constraints == [_organism("Enterocytozoon bieneusi H348")]


def test_a_constraint_both_sides_share_stays() -> None:
    intent = UserIntent(
        classification=IntentClassification.FOLLOW_UP_QUESTION,
        inferred_goal="gametocyte against asexual expression",
        is_differential=True,
        differential_sides=[
            "Plasmodium falciparum 3D7 gametocytes",
            "Plasmodium falciparum 3D7 asexual stages",
        ],
        explicit_constraints=[_organism("Plasmodium falciparum 3D7")],
    )

    assert intent.explicit_constraints == [_organism("Plasmodium falciparum 3D7")]


def _other(value: str) -> Constraint:
    return Constraint(kind=ConstraintKind.OTHER, requested_value=value, label="other")


def test_an_edit_keeps_the_value_it_swaps_in() -> None:
    """The hostdb edit from chromosome 17 to chromosome 19, which also asks the count."""
    intent = UserIntent(
        classification=IntentClassification.EDIT_STRATEGY,
        inferred_goal="change chromosome 17 to chromosome 19",
        is_differential=True,
        differential_sides=["chromosome 17", "chromosome 19"],
        explicit_constraints=[
            _organism("Mus musculus C57BL/6J"),
            _other("chromosome 19"),
        ],
    )

    assert intent.explicit_constraints == [
        _organism("Mus musculus C57BL/6J"),
        _other("chromosome 19"),
    ]


def test_a_differential_expression_request_keeps_its_comparator() -> None:
    """The fungidb request for genes up at 37 degrees against 30 degrees."""
    comparator = Constraint(
        kind=ConstraintKind.COMPARATOR,
        requested_value="37 degrees compared with 30 degrees",
        label="comparator",
    )
    intent = UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="genes upregulated at 37 degrees compared with 30 degrees",
        is_differential=True,
        differential_sides=["37 degrees", "30 degrees"],
        explicit_constraints=[_organism("Cryptococcus neoformans H99"), comparator],
    )

    assert intent.explicit_constraints == [
        _organism("Cryptococcus neoformans H99"),
        comparator,
    ]


def test_the_intent_names_no_strategy_id() -> None:
    """A strategy id the model writes is checked by nothing, so it is not held."""
    assert "referenced_strategy_ids" not in UserIntent.model_fields


_OBP = "Aedes aegypti LVP_AGWG odorant-binding protein genes on chromosome 3"


def test_an_ask_that_restates_the_request_is_no_ask() -> None:
    """The vectorbase request: the gate put all of it in its asks."""
    intent = UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="Find odorant-binding protein genes on chromosome 3.",
        asks=[_OBP],
    )

    assert intent.researcher_asks(f"{_OBP}.") == []


def test_an_ask_that_is_part_of_the_message_is_kept() -> None:
    message = f"{_OBP}. How many are there on chromosome 2?"
    intent = UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="g",
        asks=["How many are there on chromosome 2"],
    )

    assert intent.researcher_asks(message) == [
        ResearcherAsk(message=message, text="How many are there on chromosome 2")
    ]


def test_a_question_is_asked_whole() -> None:
    message = "How many of the 227 would remain at 3 TM domains?"
    intent = UserIntent(
        classification=IntentClassification.FOLLOW_UP_QUESTION, inferred_goal="g"
    )

    assert intent.researcher_asks(message) == [
        ResearcherAsk(message=message, text=message)
    ]
