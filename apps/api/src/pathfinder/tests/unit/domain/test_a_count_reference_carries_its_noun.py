"""A count reference renders with the record noun, so a noun written after it
is the same noun and renders once."""

from __future__ import annotations

import pytest

from pathfinder.domain.reply_references import render_reply
from pathfinder.domain.turn_facts import StepFact, TurnFacts

# toxodb: signal peptide 680, the ortholog step leaves 53, so it removes 627.
_TOXO = TurnFacts(
    steps=[
        StepFact(step_id="step_sp", display_name="Predicted Signal Peptide", count=680),
        StepFact(step_id="step_join", display_name="Minus", count=53),
    ],
    root_count=53,
)
_ONE = TurnFacts(steps=[StepFact(step_id="step_one", display_name="Text", count=1)])


@pytest.mark.parametrize(
    ("prose", "rendered"),
    [
        (
            "The ortholog filter removed [diff:step_sp,step_join] genes.",
            "The ortholog filter removed 627 genes.",
        ),
        ("It keeps [count:step_join] Genes, fewer.", "It keeps 53 genes, fewer."),
        ("It keeps [root] - genes.", "It keeps 53 genes."),
        ("It started from [count:step_sp] gene.", "It started from 680 genes."),
    ],
)
def test_the_record_noun_after_a_count_reference_renders_once(
    prose: str, rendered: str
) -> None:
    assert render_reply(prose, _TOXO) == rendered


def test_a_singular_count_absorbs_the_plural_noun() -> None:
    assert render_reply("It finds [count:step_one] genes.", _ONE) == (
        "It finds 1 gene."
    )


def test_another_word_after_a_count_reference_is_left_alone() -> None:
    assert render_reply("It keeps [count:step_join] genomes.", _TOXO) == (
        "It keeps 53 genes genomes."
    )
    assert render_reply("It keeps [count:step_join] of them.", _TOXO) == (
        "It keeps 53 genes of them."
    )


def test_the_noun_after_a_reference_with_no_count_is_left_alone() -> None:
    facts = TurnFacts(
        strategy_url="https://qa.toxodb.org/toxo.qa/app/workspace/strategies/1/2"
    )
    assert render_reply("[url] genes", facts) == f"{facts.strategy_url} genes"
