"""Lead arcs on a requirement's lifecycle: a comparison whose sides the model
writes as constraints, and a card of the Lead's own whose options are labels."""

from __future__ import annotations

from typing import Any

from assistant_core.models.scripted import current_scope_id, scripted_call
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.calls import CLASSIFY, classify, lead_final
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


def _constraint(kind: str, label: str, value: str, *, hard: bool) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": label,
        "requestedValue": value,
        "source": "user_explicit",
        "hard": hard,
    }


def comparison_sides(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """A comparison classified with both of its sides written as constraints."""
    del messages
    organism = SiteValues.for_site(current_scope_id.get()).organism
    return [
        scripted_call(
            CLASSIFY,
            {
                "intent": {
                    "classification": "follow_up_question",
                    "inferredGoal": "[mock] compare the name search with domains",
                    "isDifferential": True,
                    "differentialSides": COMPARED_SIDES,
                    "explicitConstraints": [
                        _constraint("organism", "organism", organism, hard=True),
                        _constraint(
                            "other",
                            "domain family",
                            "polar tube protein family",
                            hard=True,
                        ),
                        _constraint(
                            "combination",
                            "domain search alternatives",
                            "InterPro OR Pfam",
                            hard=False,
                        ),
                    ],
                }
            },
        ),
        lead_final(_COMPARED, "complete"),
    ]


def widen_card(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """A card of the Lead's own that offers two labels over an empty combine."""
    del messages
    return [
        classify("follow_up_question"),
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
