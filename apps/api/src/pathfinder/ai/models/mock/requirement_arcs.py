"""Lead arcs on a requirement's lifecycle: a comparison whose sides the reading
writes as sides, and a card of the Lead's own whose options are labels."""

from __future__ import annotations

from assistant_core.models.scripted import scripted_call
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.models.mock.arc_readings import intent_of, stated
from pathfinder.ai.models.mock.calls import lead_final
from pathfinder.ai.models.mock.site_values import SiteValues

COMPARED_SIDES = [
    "polar tube protein name search",
    "InterPro or Pfam polar tube protein domain search",
]
WIDEN_PROMPT = (
    "The intersection of the signal-peptide genes with the oocyst-expression "
    "proxy returned no genes. Which available expression setting should I relax "
    "for a broader result?"
)
WIDEN_LABELS = ["Minimum expression percentile: 0", "Protein Coding Only: all"]

_COMPARED = "The comparison is a question, so the strategy is as it was."
_WIDEN_REPLY = "[mock] The combined result is empty, so I ask how to widen it."


def comparison_sides_reading(state: PipelineState, words: str) -> UserIntent:
    del words
    organism = SiteValues.for_site(state.site_id).organism
    return intent_of(
        IntentClassification.FOLLOW_UP_QUESTION,
        stated("organism", "organism", organism),
        inferredGoal="[mock] compare the name search with domains",
        isDifferential=True,
        differentialSides=COMPARED_SIDES,
    )


def comparison_sides(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """The answer to a comparison read with both of its sides."""
    del messages
    return [lead_final(_COMPARED, "complete")]


def widen_card(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """A card of the Lead's own that offers two labels over an empty combine."""
    del messages
    return [
        scripted_call(
            "consult_user",
            {
                "reply": _WIDEN_REPLY,
                "questions": [
                    {
                        "id": "widen_expression_proxy",
                        "kind": "single_choice",
                        "prompt": WIDEN_PROMPT,
                        "dimension": "percentile",
                        "options": [{"label": label} for label in WIDEN_LABELS],
                    }
                ],
            },
        ),
    ]
