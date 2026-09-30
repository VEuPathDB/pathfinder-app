"""The phrase reading of a text expression quotes each operand of several
words; an operator word and a wildcard word are never inside the quotes."""

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
