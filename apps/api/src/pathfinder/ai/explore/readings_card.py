from __future__ import annotations

from collections.abc import Mapping

from assistant_core.graph.turn_state import ConsultQuestion
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field, JsonValue
from pydantic_ai import ModelRetry, RunContext

from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.card_reply import CardReply
from pathfinder.ai.lead.lead_consult import consult_can_ask
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import ConstraintKind

_LEAST_READINGS = 2


class _ParkedCard(CamelModel):
    model_config = ConfigDict(extra="ignore")

    questions: list[ConsultQuestion] = Field(default_factory=list)


def counted_labels(deps: LeadDeps) -> dict[str, int]:
    return {
        variant.label: variant.gene_count
        for comparison in deps.state.turn_markers.comparisons
        for variant in comparison.variants
    }


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


def _refusal(questions: list[CardQuestion], counted: Mapping[str, int]) -> str | None:
    if len(questions) != 1:
        return (
            f"The readings card asks one question, and this one asks {len(questions)}. "
            "Ask one question whose options are the readings you counted."
        )
    [question] = questions
    labels = [option.label for option in question.options]
    if len(labels) < _LEAST_READINGS:
        return (
            "The readings card offers two readings at least, each one counted with "
            "propose_readings. With fewer, end on the reply alone."
        )
    uncounted = [label for label in labels if label not in counted]
    if uncounted:
        return (
            f"The options {uncounted} name no reading this turn counted. Count each "
            f"with propose_readings first, or label each option exactly as counted: "
            f"{sorted(counted) or 'none counted yet'}."
        )
    return _form_refusal(question)


async def readings_card_can_ask(
    ctx: RunContext[LeadDeps], questions: list[CardQuestion], *, reply: CardReply
) -> None:
    refusal = _refusal(questions, counted_labels(ctx.deps))
    if refusal is not None:
        raise ModelRetry(refusal)
    await consult_can_ask(ctx, questions, reply=reply)


def card_labels(args: Mapping[str, JsonValue]) -> list[str]:
    card = _ParkedCard.model_validate(args)
    return [option.label for question in card.questions for option in question.options]
