"""The budget one Lead turn runs under, and the reply it ends with at the cap."""

from __future__ import annotations

from pydantic_ai.usage import RunUsage, UsageLimits

from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.platform.config import get_settings

# One turn's ceiling on the Lead's own model requests, and on the tool calls
# they make. A sub-agent pass runs under a ceiling of its own.
LEAD_TURN_CALL_LIMIT = 80
# A turn outside PathFinder's scope answers in two sentences and reaches no
# tool, so it never needs what an investigation spends.
OFF_TOPIC_TURN_TOKEN_LIMIT = 40_000


def lead_usage_limits() -> UsageLimits:
    """The ceiling for the Lead's own run in one turn, as its own object."""
    return UsageLimits(
        request_limit=LEAD_TURN_CALL_LIMIT,
        tool_calls_limit=LEAD_TURN_CALL_LIMIT,
        total_tokens_limit=get_settings().lead_turn_token_limit,
    )


def _budget_reached_message(*, calls: int, tokens: int) -> str:
    return (
        f"I stopped this turn at its budget of {calls} model calls and "
        f"{tokens} tokens. Narrow the request and send it again, and I will "
        f"start a fresh turn on it."
    )


def lead_turn_budget_message() -> str:
    """What the user reads when a turn spends the ceiling it runs under."""
    return _budget_reached_message(
        calls=LEAD_TURN_CALL_LIMIT,
        tokens=get_settings().lead_turn_token_limit,
    )


def off_topic_budget_stop(usage: RunUsage, intent: UserIntent | None) -> str | None:
    """The reply an out-of-scope turn ends with once it passes its budget.

    The run accumulates into the ``RunUsage`` the turn handed it, so reading
    that object after each event is what tells the turn it has spent enough.
    """
    if intent is None or intent.classification is not IntentClassification.OFF_TOPIC:
        return None
    if usage.total_tokens <= OFF_TOPIC_TURN_TOKEN_LIMIT:
        return None
    return _budget_reached_message(
        calls=LEAD_TURN_CALL_LIMIT,
        tokens=OFF_TOPIC_TURN_TOKEN_LIMIT,
    )
