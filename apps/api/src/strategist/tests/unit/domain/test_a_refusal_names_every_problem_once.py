import pytest
from pydantic import ValidationError

from strategist.domain.refusal import (
    KeyUse,
    Problem,
    Problems,
    RefusalKey,
    RefusalLedger,
)

KINASE = RefusalKey(check="unknown_names", criterion="c_kinase")
TAXON = RefusalKey(check="bad_value", search="GenesByTaxon", parameter="organism")


def test_a_repeated_problem_is_named_once() -> None:
    p = Problem(key=KINASE, sentence="kinase is not a known name.")
    q = Problem(key=TAXON, sentence="organism has no value.")
    assert Problems(found=(p, p, q)).found == (p, q)


def test_one_key_with_two_sentences_keeps_both() -> None:
    p = Problem(key=KINASE, sentence="first.")
    q = Problem(key=KINASE, sentence="second.")
    assert Problems(found=(p, q)).found == (p, q)


def test_a_sentence_collapses_its_whitespace() -> None:
    assert Problem(key=KINASE, sentence="a\n  b").sentence == "a b"
    assert Problem(key=KINASE, sentence="  a\t\tb \n").sentence == "a b"


def test_a_blank_sentence_is_refused() -> None:
    with pytest.raises(ValidationError):
        Problem(key=KINASE, sentence=" \n ")


def test_a_key_needs_its_check() -> None:
    with pytest.raises(ValidationError):
        RefusalKey(check="")


def test_one_problem_reads_as_its_sentence() -> None:
    assert Problems.one(KINASE, "x").text() == "x"


def test_several_problems_read_as_a_numbered_list() -> None:
    two = Problems.one(KINASE, "x").plus(Problems.one(TAXON, "y"))
    assert two.text() == "2 problems:\n1. x\n2. y"


def test_no_problems_are_empty() -> None:
    assert Problems().empty
    assert not Problems.one(KINASE, "x").empty
    assert Problems().text() == ""


def test_plus_drops_a_problem_already_named() -> None:
    both = Problems.one(KINASE, "x").plus(Problems.one(KINASE, "x"))
    assert both.found == (Problem(key=KINASE, sentence="x"),)


def test_keys_are_distinct_and_in_order() -> None:
    found = Problems(
        found=(
            Problem(key=TAXON, sentence="a"),
            Problem(key=KINASE, sentence="b"),
            Problem(key=TAXON, sentence="c"),
        )
    )
    assert found.keys() == (TAXON, KINASE)


def test_a_label_joins_what_the_key_names() -> None:
    key = RefusalKey(check="unknown_names", criterion="c_kinase", search="GenesByTaxon")
    assert key.label() == "c_kinase / GenesByTaxon"
    assert TAXON.label() == "GenesByTaxon / organism"
    assert RefusalKey(check="unknown_names").label() == "unknown_names"


def test_under_fills_only_empty_fields() -> None:
    key = RefusalKey(check="unknown_names", criterion="c")
    assert key.under(criterion="r1", search="s") == RefusalKey(
        check="unknown_names", criterion="c", search="s"
    )


def test_problems_under_place_every_key() -> None:
    found = Problems.one(RefusalKey(check="a"), "x").plus(Problems.one(KINASE, "y"))
    placed = found.under(criterion="r1", search="s")
    assert placed.keys() == (
        RefusalKey(check="a", criterion="r1", search="s"),
        RefusalKey(check="unknown_names", criterion="c_kinase", search="s"),
    )


def test_a_charge_counts_each_key_once_per_call() -> None:
    a1 = Problem(key=KINASE, sentence="first.")
    a2 = Problem(key=KINASE, sentence="second.")
    b = Problem(key=TAXON, sentence="third.")
    first = RefusalLedger().charge(Problems(found=(a1, a2, b)), 2)
    assert first.refused.found == (a1, a2, b)
    assert first.spent.empty
    assert first.ledger.used(KINASE) == 1
    assert first.ledger.used(TAXON) == 1

    second = first.ledger.charge(Problems(found=(a1,)), 2)
    assert second.refused.found == (a1,)
    assert second.ledger.used(KINASE) == 2

    third = second.ledger.charge(Problems(found=(a1, b)), 2)
    assert third.spent.found == (a1,)
    assert third.refused.found == (b,)
    assert third.ledger.used(KINASE) == 2
    assert third.ledger.used(TAXON) == 2


def test_an_unknown_key_is_unused() -> None:
    assert RefusalLedger().used(KINASE) == 0


def test_a_use_is_at_least_one() -> None:
    with pytest.raises(ValidationError):
        KeyUse(key=KINASE, used=0)


def test_a_ledger_survives_its_json_form() -> None:
    ledger = (
        RefusalLedger()
        .charge(Problems.one(KINASE, "x").plus(Problems.one(TAXON, "y")), 3)
        .ledger
    )
    dumped = ledger.model_dump(mode="json", by_alias=True)
    assert RefusalLedger.model_validate(dumped) == ledger
    assert dumped["uses"][0]["key"]["check"] == "unknown_names"


def test_a_problem_differing_only_in_whitespace_is_named_once() -> None:
    found = Problems(
        found=(
            Problem(key=KINASE, sentence="x y"),
            Problem(key=KINASE, sentence=" x\n y "),
        )
    )
    assert found.found == (Problem(key=KINASE, sentence="x y"),)
