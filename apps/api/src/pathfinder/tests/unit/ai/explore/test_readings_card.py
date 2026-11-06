from __future__ import annotations

from typing import Any

import pytest
from assistant_core.graph.turn_state import ConsultOption
from pydantic import JsonValue, ValidationError
from pydantic_ai import ModelRetry, RunContext

from pathfinder.ai.explore.readings_card import (
    card_labels,
    counted_labels,
    readings_card_can_ask,
)
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.services.experiment.search_reads import SearchCount
from pathfinder.tests._support.run_context import lead_run_context

CALL_ID = "call_readings_card"
FIRST_LABEL = "Genes with a predicted signal peptide"
SECOND_LABEL = "Every protein-coding gene"
_COUNTS = {FIRST_LABEL: 479, SECOND_LABEL: 5389}
_PROMPT = "Which reading should the strategy build?"


@pytest.fixture
def ctx() -> RunContext[LeadDeps]:
    context = lead_run_context(tool_call_id=CALL_ID)
    for label, count in _COUNTS.items():
        counted = SearchCount(
            label=label, search_name="GenesWithSignalPeptide", gene_count=count
        )
        context.deps.state.turn_markers.record_comparison(counted.fact())
    return context


def card(*labels: str, allow_notes: bool = False, **fields: Any) -> CardQuestion:
    return CardQuestion(
        id="reading",
        prompt=_PROMPT,
        options=[ConsultOption(label=label) for label in labels],
        allow_notes=allow_notes,
        **fields,
    )


def consult_args(*labels: str) -> dict[str, JsonValue]:
    return {
        "reply": "Two readings the site can build answer this question.",
        "questions": [
            {
                "id": "reading",
                "prompt": _PROMPT,
                "options": [{"label": label} for label in labels],
                "allowNotes": False,
            }
        ],
    }


def test_the_counted_labels_are_read_from_the_turn(ctx: RunContext[LeadDeps]) -> None:
    assert counted_labels(ctx.deps) == _COUNTS


async def test_a_card_of_the_counted_readings_is_asked(
    ctx: RunContext[LeadDeps],
) -> None:
    await readings_card_can_ask(
        ctx, [card(FIRST_LABEL, SECOND_LABEL)], reply="Two readings."
    )

    assert ctx.deps.state.turn_markers.card_stand_ins == {CALL_ID: {}}


async def test_an_uncounted_reading_is_refused(ctx: RunContext[LeadDeps]) -> None:
    with pytest.raises(ModelRetry, match="propose_readings"):
        await readings_card_can_ask(
            ctx, [card(FIRST_LABEL, "a reading never counted")], reply="r"
        )

    assert ctx.deps.state.turn_markers.card_stand_ins == {}


async def test_a_card_with_no_reading_is_refused(ctx: RunContext[LeadDeps]) -> None:
    with pytest.raises(ModelRetry, match="two"):
        await readings_card_can_ask(ctx, [card()], reply="r")


def test_a_card_of_one_counted_reading_is_refused(ctx: RunContext[LeadDeps]) -> None:
    assert FIRST_LABEL in counted_labels(ctx.deps)

    with pytest.raises(ValidationError, match="no choice"):
        card(FIRST_LABEL)


async def test_a_card_that_takes_notes_is_refused(ctx: RunContext[LeadDeps]) -> None:
    with pytest.raises(ModelRetry, match="allowNotes"):
        await readings_card_can_ask(
            ctx, [card(FIRST_LABEL, SECOND_LABEL, allow_notes=True)], reply="r"
        )


async def test_two_questions_are_refused(ctx: RunContext[LeadDeps]) -> None:
    with pytest.raises(ModelRetry, match="one question"):
        await readings_card_can_ask(
            ctx,
            [card(FIRST_LABEL, SECOND_LABEL), card(FIRST_LABEL, SECOND_LABEL)],
            reply="r",
        )


async def test_a_typed_dimension_is_refused(ctx: RunContext[LeadDeps]) -> None:
    typed = card(FIRST_LABEL, SECOND_LABEL, dimension=ConstraintKind.ORGANISM)

    with pytest.raises(ModelRetry, match="dimension"):
        await readings_card_can_ask(ctx, [typed], reply="r")


async def test_a_stand_in_is_refused(ctx: RunContext[LeadDeps]) -> None:
    standing = card(FIRST_LABEL, SECOND_LABEL, replaces=["R1"])

    with pytest.raises(ModelRetry, match="replaces"):
        await readings_card_can_ask(ctx, [standing], reply="r")


def test_the_labels_of_a_parked_card_are_read_in_order() -> None:
    assert card_labels(consult_args(FIRST_LABEL, SECOND_LABEL)) == [
        FIRST_LABEL,
        SECOND_LABEL,
    ]
