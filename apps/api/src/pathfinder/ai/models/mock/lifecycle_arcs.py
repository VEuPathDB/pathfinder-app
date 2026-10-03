"""Lead arcs that state requirements the thread's lifecycle is derived from: a
narrower organism stated with no withdrawal, and a requirement taken back by
its dimension and value alone."""

from __future__ import annotations

from typing import Any

from assistant_core.models.scripted import current_scope_id, scripted_call
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.calls import CLASSIFY, lead_final
from pathfinder.ai.models.mock.site_values import SiteValues

# The requirement the withdrawal arc takes back, as the classifier states it.
WITHDRAWN_VALUE = "transmembrane domain"

_NARROWED = "The strategy now reads the narrower organism."
_WITHDRAWN = "The transmembrane domain requirement is taken back."


def _constraint(kind: str, label: str, value: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": label,
        "requestedValue": value,
        "source": "user_explicit",
        "hard": True,
    }


def _classified(**intent: Any) -> ToolCallPart:
    return scripted_call(
        CLASSIFY,
        {
            "intent": {
                "classification": "edit_strategy",
                "inferredGoal": "[mock] change a requirement",
                **intent,
            }
        },
    )


def narrowed_organism(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """An edit that states the site's organism and withdraws nothing."""
    del messages
    organism = SiteValues.for_site(current_scope_id.get()).organism
    return [
        _classified(
            explicitConstraints=[_constraint("organism", "organism", organism)]
        ),
        lead_final(_NARROWED, "await_user"),
    ]


def withdrawn_requirement(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """An edit that takes one requirement back by its dimension and value."""
    del messages
    return [
        _classified(withdrawn=[_constraint("other", "domain", WITHDRAWN_VALUE)]),
        lead_final(_WITHDRAWN, "await_user"),
    ]
