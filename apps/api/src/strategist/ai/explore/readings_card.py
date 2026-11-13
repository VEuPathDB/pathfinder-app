from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from assistant_core.graph.turn_state import ConsultQuestion
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field, JsonValue
from pydantic_ai import ModelRetry, RunContext

from strategist.ai.lead.card_question import CardQuestion
from strategist.ai.lead.card_reply import CardReply
from strategist.ai.lead.lead_consult import consult_can_ask
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.domain.strategy.constraints import ConstraintKind
from strategist.domain.strategy.reading_plan import OfferedReading

_LEAST_READINGS = 2

READINGS_CARD_DESCRIPTION: Final = (
    "End the turn on the readings card: the researcher picks the plan Build frames.\n\n"
    "Ask exactly one question. Its options are two or more plans this turn proposed "
    "with propose_readings, each labelled exactly as returned, with its gene count, or "
    "not counted yet, in the option's description. Leave the question's dimension at "
    "untyped, set allowNotes to false, and leave replaces empty. Put what the plans mean "
    "in reply, which streams above the card.\n\n"
    "This pauses the turn. A pick hands the conversation and the picked plan to Build. "
    "With fewer than two proposals, end on the reply alone."
)


class _ParkedCard(CamelModel):
    model_config = ConfigDict(extra="ignore")

    questions: list[ConsultQuestion] = Field(default_factory=list)


def proposals(deps: LeadDeps) -> list[OfferedReading]:
    offered = deps.state.domain.offered_readings
    return [
        offered[label]
        for label in deps.state.turn_markers.proposed_readings
        if label in offered
    ]


def proposal_counts(deps: LeadDeps) -> dict[str, int | None]:
    return {reading.label: reading.gene_count for reading in proposals(deps)}


def _form_refusal(question: CardQuestion) -> str | None:
    wrong = [
        refusal
        for broken, refusal in (
            (
                question.dimension is not ConstraintKind.UNTYPED,
                "The readings card states no dimension. Leave dimension at untyped.",
            ),
            (
                question.allow_notes,
                "The readings card takes no note. Set allowNotes to false.",
            ),
            (
                bool(question.replaces),
                "The readings card replaces no requirement. Leave replaces empty.",
            ),
        )
        if broken
    ]
    return wrong[0] if wrong else None


def _refusal(
    questions: list[CardQuestion], counted: Mapping[str, int | None]
) -> str | None:
    if len(questions) != 1:
        return (
            f"The readings card asks one question, and this one asks {len(questions)}. "
            "Ask one question whose options are the plans you proposed."
        )
    [question] = questions
    labels = [option.label for option in question.options]
    if len(labels) < _LEAST_READINGS:
        return (
            "The readings card offers two proposals at least, each one made with "
            "propose_readings. With fewer, end on the reply alone."
        )
    uncounted = [label for label in labels if label not in counted]
    if uncounted:
        return (
            f"The options {uncounted} name no plan this turn proposed. Propose each "
            f"with propose_readings first, or label each option exactly as returned: "
            f"{sorted(counted) or 'none proposed yet'}."
        )
    return _form_refusal(question)


async def readings_card_can_ask(
    ctx: RunContext[LeadDeps], questions: list[CardQuestion], *, reply: CardReply
) -> None:
    refusal = _refusal(questions, proposal_counts(ctx.deps))
    if refusal is not None:
        raise ModelRetry(refusal)
    await consult_can_ask(ctx, questions, reply=reply)


def card_labels(args: Mapping[str, JsonValue]) -> list[str]:
    card = _ParkedCard.model_validate(args)
    return [option.label for question in card.questions for option in question.options]
