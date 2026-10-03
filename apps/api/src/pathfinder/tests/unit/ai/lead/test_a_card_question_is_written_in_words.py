"""A question the card asks is read by the researcher before the facts exist,
so it carries no reference; a value it states is written in words."""

from __future__ import annotations

import pytest
from assistant_core.graph.turn_state import ConsultOption
from pydantic import ValidationError

from pathfinder.ai.lead.card_question import CardQuestion


def test_a_reference_in_the_prompt_is_refused() -> None:
    with pytest.raises(ValidationError) as refused:
        CardQuestion(
            id="q1",
            prompt=(
                "Enter a numeric value; the site threshold is [value:c_tm.max_tm] "
                "and its setting is [source:c_tm.min_tm]."
            ),
        )

    assert "['[value:c_tm.max_tm]', '[source:c_tm.min_tm]']" in str(refused.value)
    assert "write the value in words from the sheet you read" in str(refused.value)


def test_a_reference_in_an_option_label_is_refused() -> None:
    with pytest.raises(ValidationError):
        CardQuestion(
            id="q1",
            prompt="Which minimum?",
            options=[
                ConsultOption(label="the site threshold, [value:c_pep.min]"),
                ConsultOption(label="two peptides"),
            ],
        )


def test_a_question_in_words_stands() -> None:
    question = CardQuestion(
        id="q1",
        prompt="How many unique peptides must support a gene? The site's threshold is 2.",
        context="[2] is the site's default for this search.",
    )

    assert question.prompt.endswith("The site's threshold is 2.")
