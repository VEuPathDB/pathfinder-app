"""The budget one Lead turn runs under, and the reply it ends with at the cap."""

from __future__ import annotations

import re
from collections.abc import Sequence

from assistant_core.graph.tool_summary import count_noun
from pydantic_ai.usage import RunUsage, UsageLimits

from pathfinder.ai.graph.state import VerificationDigest
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.ledger import InvestigationLedger
from pathfinder.ai.lead.reply_claims import machine_words
from pathfinder.ai.tools.standalone.graph_helpers import build_step_response
from pathfinder.domain.strategy.constraints import OpenQuestion
from pathfinder.domain.strategy.session import StrategySession, strategy_root_id
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


_GENE_RECORD_TYPES = frozenset({"gene", "transcript"})
_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


def _with_link(line: str, url: str | None) -> str:
    return line if url is None else f"{line} It is on VEuPathDB at {url}."


def _strategy_state(ledger: InvestigationLedger, session: StrategySession) -> str:
    """What the strategy holds, with the count and link the ledger's build cites."""
    graph = session.graph
    if graph is None or not graph.steps:
        return "Nothing was built."
    held = f"The strategy holds {count_noun(len(graph.steps), 'step')}"
    url = ledger.build.wdk_url
    root_id = strategy_root_id(graph, session.sync_state)
    if root_id is None:
        return _with_link(f"{held}.", url)
    title = build_step_response(graph, graph.steps[root_id]).display_name
    count = next(
        (n.count for n in ledger.build.node_results if n.node_id == root_id), None
    )
    if count is None:
        return _with_link(f'{held}; the final step is "{title}".', url)
    noun = "gene" if graph.record_type in _GENE_RECORD_TYPES else "record"
    returns = f'the final step "{title}" returns {count_noun(count, noun)}'
    return _with_link(f"{held}; {returns}.", url)


def _verdict(digest: VerificationDigest) -> str:
    """The check's verdict, with the first sentence of an objection when it is plain."""
    if digest.success:
        return "Verification passed."
    first = _SENTENCE_END.split(digest.prose.strip(), maxsplit=1)[0]
    if machine_words(first):
        return "Verification objected."
    return f"Verification objected: {first}"


def budget_stop_report(
    ledger: InvestigationLedger,
    session: StrategySession,
    questions: Sequence[OpenQuestion],
) -> str:
    """What a turn at its whole budget produced, then the stop itself."""
    digest = ledger.verification.digest
    parts = [
        _strategy_state(ledger, session),
        *([_verdict(digest)] if digest is not None else []),
        *(q.question for q in questions),
        lead_turn_budget_message(),
    ]
    return "\n\n".join(parts)


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
