"""The Lead reads the conversation's last exchanges before the latest message."""

from __future__ import annotations

from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.lead_pins import pinned_conversation
from pathfinder.domain.exchanges import Exchange, exchanges_section
from pathfinder.tests._support.run_context import lead_run_context


def test_a_conversation_with_no_exchange_pins_nothing() -> None:
    assert [pinned_conversation(lead_run_context())] == [None]


def test_the_pin_is_the_conversations_last_exchanges() -> None:
    ctx = lead_run_context(user_prompt="Show me that same sample again.")
    exchanges = [
        Exchange(
            said="Show me a sample of five genes.",
            reply="ENSMUSG00000035929, ENSMUSG00000060550 and three more.",
        )
    ]
    for exchange in exchanges:
        ctx.deps.state.domain.record_exchange(exchange)

    assert pinned_conversation(ctx) == exchanges_section(exchanges)


def test_the_instructions_send_a_reference_to_an_earlier_reply_to_the_section() -> None:
    assert (
        '- **A message that points at an earlier reply is answered from "The '
        'conversation so far".**'
    ) in LEAD_INSTRUCTIONS


def test_a_record_shown_earlier_is_cited_without_reading_it_again() -> None:
    assert (
        "A record those replies listed is cited with ``[record:<id>]`` as it "
        "stands, never read again to show it."
    ) in " ".join(LEAD_INSTRUCTIONS.split())
