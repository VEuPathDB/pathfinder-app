"""The phrase reading of a text expression quotes each operand of several
words; an operator word and a wildcard word are never inside the quotes. The
words reading of a quoted text removes the quotes around each phrase."""

from __future__ import annotations

import pytest

from pathfinder.domain.strategy.text_expression import TextExpression


@pytest.mark.parametrize(
    ("text", "phrased"),
    [
        (
            "variant-specific surface protein OR VSP",
            '"variant-specific surface protein" OR VSP',
        ),
        ("cytochrome P450", '"cytochrome P450"'),
        (
            "heat shock protein AND NOT small heat shock",
            '"heat shock protein" AND NOT "small heat shock"',
        ),
        (
            "protein kinase* OR cyclin dependent",
            'protein kinase* OR "cyclin dependent"',
        ),
    ],
)
def test_each_operand_of_several_words_is_quoted(text: str, phrased: str) -> None:
    assert TextExpression(text=text).phrase_reading() == phrased


def test_a_text_no_operand_of_which_is_a_phrase_has_no_phrase_reading() -> None:
    texts = ["VSP OR VSG", "P450", '"cytochrome P450"', "kinase*", "protein kinase*"]

    assert [TextExpression(text=t).phrase_reading() for t in texts] == [None] * 5


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ('"GPI anchored"', "GPI anchored"),
        (
            '"variant-specific surface protein" OR VSP',
            "variant-specific surface protein OR VSP",
        ),
        ('"VSP" OR "variant surface protein"', '"VSP" OR variant surface protein'),
    ],
)
def test_each_quoted_phrase_of_several_words_is_unquoted(text: str, words: str) -> None:
    assert TextExpression(text=text).words_reading() == words


def test_a_text_that_quotes_no_phrase_has_no_words_reading() -> None:
    texts = ["GPI anchored", '"VSP"', '"VSP" OR VSG', "kinase*", '"GPI anchored']

    assert [TextExpression(text=t).words_reading() for t in texts] == [None] * 5
