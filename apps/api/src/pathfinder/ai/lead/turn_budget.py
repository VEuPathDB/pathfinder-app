"""The budget one Lead turn runs under, and the reply it ends with at the cap."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from assistant_core.graph.tool_summary import count_noun
from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.usage import RunUsage, UsageLimits

from pathfinder.ai.graph.state import VerificationDigest
from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.ai.lead.ledger import InvestigationLedger
from pathfinder.ai.lead.reply_claims import machine_words
from pathfinder.ai.tools.standalone.graph_helpers import (
    build_step_response,
    counted_records,
)
from pathfinder.domain.strategy.build_outcome import built_counts
from pathfinder.domain.strategy.questions import OpenQuestion
from pathfinder.domain.strategy.session import StrategySession, strategy_root_id
from pathfinder.domain.strategy.step_words import AddedSearch
from pathfinder.platform.config import get_settings
from pathfinder.services.strategies.result_list import live_result_list_url

# One turn's ceiling on the Lead's own model requests, and on the tool calls
# they make. A sub-agent pass runs under a ceiling of its own.
LEAD_TURN_CALL_LIMIT = 80
CACHE_READ_WEIGHT = 0.1


def lead_usage_limits() -> UsageLimits:
    """The ceiling for the Lead's own run in one turn, as its own object."""
    return UsageLimits(
        request_limit=LEAD_TURN_CALL_LIMIT,
        tool_calls_limit=LEAD_TURN_CALL_LIMIT,
    )


def counted_tokens(usage: RunUsage) -> int:
    cached = usage.cache_read_tokens
    fresh = usage.input_tokens - cached + usage.output_tokens
    return fresh + round(cached * CACHE_READ_WEIGHT)


@dataclass
class TurnTokenBudget(AbstractCapability[Any]):
    limit: int

    async def before_model_request(
        self, ctx: RunContext[Any], request_context: ModelRequestContext
    ) -> ModelRequestContext:
        spent = counted_tokens(ctx.usage)
        if spent > self.limit:
            msg = f"The turn counted {spent} tokens, over its budget of {self.limit}."
            raise UsageLimitExceeded(msg)
        return request_context


def lead_token_budget() -> TurnTokenBudget:
    return TurnTokenBudget(limit=get_settings().lead_turn_token_limit)


def _spent_limit(spent: RunUsage, limits: UsageLimits, token_limit: int) -> str:
    calls = limits.request_limit
    if counted_tokens(spent) > token_limit:
        return f"{token_limit} tokens"
    if calls is not None and spent.requests >= calls:
        return count_noun(calls, "model call")
    return f"{limits.tool_calls_limit} tool calls"


_AFTER_A_BUILD = (
    "The strategy above is built but not yet checked. Say continue and I will "
    "check it and explain it."
)
_AFTER_A_CHECK = (
    "The strategy above is built and checked. Say continue and I will go on from there."
)
_NARROW = "Narrow the request and send it again, and I will start a fresh turn on it."


def _advice(*, built: bool, checked: bool) -> str:
    if not built:
        return _NARROW
    return _AFTER_A_CHECK if checked else _AFTER_A_BUILD


def lead_turn_budget_message(
    spent: RunUsage,
    limits: UsageLimits,
    *,
    token_limit: int,
    built: bool,
    checked: bool,
) -> str:
    """What the user reads when a turn spends a ceiling it runs under."""
    advice = _advice(built=built, checked=checked)
    return (
        f"I stopped this turn at its budget of "
        f"{_spent_limit(spent, limits, token_limit)}. {advice}"
    )


_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


def _with_link(line: str, url: str | None) -> str:
    return line if url is None else f"{line} It is on VEuPathDB at {url}."


_OUT_OF_DATE = (
    "The strategy changed on VEuPathDB after this conversation built it, so the "
    "count recorded here is out of date."
)


def _strategy_state(ledger: InvestigationLedger, session: StrategySession) -> str:
    """What the strategy holds, its recorded count and the link to its live root.

    A build the ledger marks stale cites neither.
    """
    graph = session.graph
    if graph is None or not graph.steps:
        return "Nothing was built."
    held = f"The strategy holds {count_noun(len(graph.steps), 'step')}"
    url = live_result_list_url(session.site_id, session.sync_state)
    root_id = strategy_root_id(graph, session.sync_state)
    if root_id is None:
        if ledger.build.stale_build is not None:
            return f"{held}. {_OUT_OF_DATE}"
        return _with_link(f"{held}.", url)
    title = build_step_response(graph, graph.steps[root_id]).display_name
    if ledger.build.stale_build is not None:
        return f'{held}; the final step is "{title}". {_OUT_OF_DATE}'
    count = built_counts(graph, session.sync_state).of(root_id)
    if count is None:
        return _with_link(f'{held}; the final step is "{title}".', url)
    returns = (
        f'the final step "{title}" returns {counted_records(count, graph.record_type)}'
    )
    return _with_link(f"{held}; {returns}.", url)


def _verdict(digest: VerificationDigest) -> str:
    """The check's verdict, with the first sentence of what failed when it is plain."""
    if digest.success and digest.pending_checks:
        pending = digest.pending_checks
        return (
            f"Verification passed, {count_noun(len(pending), 'check')} pending: "
            f"{', '.join(pending)}."
        )
    if digest.success:
        return "Verification passed."
    if digest.not_checked:
        return "Not verified: the site did not answer the check."
    first = _SENTENCE_END.split(digest.reason.strip(), maxsplit=1)[0]
    if machine_words(first):
        return "Verification objected."
    return f"Verification objected: {first}"


def _stands_for(step: AddedSearch) -> str:
    """The words the step stands for, and why it runs its search when recorded."""
    if step.rationale is None:
        return step.criterion_text
    return f"{step.criterion_text}; {step.rationale.short}"


def _this_turn(turn: TurnMarkers) -> str:
    """What this turn wrote to the strategy, naming each step it added."""
    added = turn.added_searches
    if added:
        named = "; ".join(
            f'"{step.search_display_name}" ({_stands_for(step)})' for step in added
        )
        return f"This turn added {count_noun(len(added), 'step')}: {named}."
    if turn.changed_strategy:
        return "This turn changed the strategy and added no step."
    return "This turn changed nothing."


def _verification(ledger: InvestigationLedger, session: StrategySession) -> list[str]:
    """The verdict on the strategy as it stands, or that no check judged it."""
    digest = ledger.verification.digest
    if digest is not None:
        return [_verdict(digest)]
    graph = session.graph
    if graph is None or not graph.steps:
        return []
    return ["The strategy was not verified this turn."]


def budget_stop_report(
    ledger: InvestigationLedger,
    session: StrategySession,
    turn: TurnMarkers,
    questions: Sequence[OpenQuestion],
    spent: RunUsage,
    limits: UsageLimits,
) -> str:
    """What a turn at its whole budget produced, then the stop itself."""
    parts = [
        _strategy_state(ledger, session),
        _this_turn(turn),
        *_verification(ledger, session),
        *(q.question for q in questions),
        lead_turn_budget_message(
            spent,
            limits,
            token_limit=get_settings().lead_turn_token_limit,
            built=turn.built or turn.changed_strategy,
            checked=ledger.verification.digest is not None,
        ),
    ]
    return "\n\n".join(parts)
