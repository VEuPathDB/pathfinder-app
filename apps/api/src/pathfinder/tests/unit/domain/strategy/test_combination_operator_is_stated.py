"""A stated combination's operator is the researcher's connective, not the classifier's."""

from __future__ import annotations

from pathfinder.domain.strategy.constraints import (
    CombinationRequest,
    Constraint,
    ConstraintKind,
    ConstraintSource,
    combination_operator_is_stated,
    message_states_constraint,
    read_combination,
)
from pathfinder.tests.unit.domain.strategy._vaccine_request import (
    VACCINE,
    VACCINE_TERMS,
)

SURFACE = "genes with a signal peptide or a GPI anchor"


def _request(operator: str, terms: list[str]) -> CombinationRequest:
    parsed = CombinationRequest.parse(f" {operator} ".join(terms))
    assert parsed is not None
    return parsed


def _combination(value: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.COMBINATION,
        requested_value=value,
        label="how the evidence combines",
        source=ConstraintSource.USER_EXPLICIT,
    )


class TestTheMeasuredVaccineSentence:
    def test_the_inner_ors_are_not_the_top_level_operator(self) -> None:
        assert not combination_operator_is_stated(
            VACCINE, _request("OR", VACCINE_TERMS)
        )

    def test_the_connectives_read_are_the_commas_and_the_final_and(self) -> None:
        reading = read_combination(VACCINE, _request("OR", VACCINE_TERMS))

        assert reading is not None
        assert [(c.text, c.operator) for c in reading.connectives] == [
            (", ", "AND"),
            (", ", "AND"),
            (", and ", "AND"),
        ]

    def test_the_same_terms_joined_by_and_are_stated(self) -> None:
        assert combination_operator_is_stated(VACCINE, _request("AND", VACCINE_TERMS))

    def test_the_or_constraint_is_not_what_the_message_states(self) -> None:
        or_value = " OR ".join(VACCINE_TERMS)
        and_value = " AND ".join(VACCINE_TERMS)

        assert not message_states_constraint(VACCINE, _combination(or_value))
        assert message_states_constraint(VACCINE, _combination(and_value))


class TestConnectives:
    def test_an_or_between_two_terms_states_or(self) -> None:
        terms = ["signal peptide", "GPI anchor"]

        assert combination_operator_is_stated(SURFACE, _request("OR", terms))
        assert not combination_operator_is_stated(SURFACE, _request("AND", terms))

    def test_terms_out_of_message_order_are_read_in_message_order(self) -> None:
        request = _request("OR", ["GPI anchor", "signal peptide"])
        reading = read_combination(SURFACE, request)

        assert reading is not None
        assert [(c.before, c.after) for c in reading.connectives] == [
            ("signal peptide", "GPI anchor"),
        ]
        assert combination_operator_is_stated(SURFACE, request)

    def test_an_inner_or_under_an_and_is_an_alternative_within_the_term(
        self,
    ) -> None:
        message = (
            "genes expressed in late schizonts or merozoites with a signal peptide"
        )
        terms = ["expressed in late schizonts or merozoites", "signal peptide"]

        assert combination_operator_is_stated(message, _request("AND", terms))
        assert not combination_operator_is_stated(message, _request("OR", terms))

    def test_a_comma_list_takes_the_operator_of_its_final_conjunction(self) -> None:
        message = "genes expressed in gametocytes, ookinetes, or sporozoites"
        terms = ["expressed in gametocytes", "ookinetes", "sporozoites"]

        assert combination_operator_is_stated(message, _request("OR", terms))
        assert not combination_operator_is_stated(message, _request("AND", terms))

    def test_either_makes_a_bare_list_an_alternative(self) -> None:
        message = "genes that carry either a signal peptide, a GPI anchor"
        terms = ["signal peptide", "GPI anchor"]

        assert combination_operator_is_stated(message, _request("OR", terms))

    def test_and_or_states_an_or(self) -> None:
        message = "genes with a signal peptide and/or a GPI anchor"
        terms = ["signal peptide", "GPI anchor"]

        assert combination_operator_is_stated(message, _request("OR", terms))

    def test_a_named_union_states_or_over_an_and_list(self) -> None:
        message = (
            "take genes with a signal peptide and genes with a GPI anchor "
            "and union the two"
        )
        terms = ["signal peptide", "GPI anchor"]

        assert combination_operator_is_stated(message, _request("OR", terms))
        assert not combination_operator_is_stated(message, _request("AND", terms))

    def test_terms_that_share_a_phrase_read_the_words_between_them(self) -> None:
        message = "genes up- or down-regulated in gametocytes"
        terms = ["up-regulated in gametocytes", "down-regulated in gametocytes"]

        assert combination_operator_is_stated(message, _request("OR", terms))

    def test_a_term_the_message_does_not_carry_reads_nothing(self) -> None:
        request = _request("OR", ["signal peptide", "apicoplast targeting"])

        assert read_combination(SURFACE, request) is None
        assert not combination_operator_is_stated(SURFACE, request)


def test_an_organism_is_still_stated_with_its_genus_abbreviated() -> None:
    organism = Constraint(
        kind=ConstraintKind.ORGANISM,
        requested_value="Plasmodium falciparum",
        label="organism",
    )

    assert message_states_constraint("Find P. falciparum kinases.", organism)
