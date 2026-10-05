"""A dispatched sub-agent carries the conversation's last exchanges, and reads
them in the same section the Lead does."""

from __future__ import annotations

from pathfinder.ai.agents._instructions import pinned_conversation_so_far
from pathfinder.ai.agents.frame import _FRAME_INSTRUCTIONS
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.intent import UserIntent
from pathfinder.domain.exchanges import Exchange, exchanges_section
from pathfinder.tests._support.run_context import lead_run_context, run_context_for

_RECOMMENDED = Exchange(
    said="Which RNA-Seq experiment would you recommend for gametocytes?",
    reply="I recommend Transcriptomes of seven sexual and asexual life stages.",
)


def test_a_dispatched_sub_agent_carries_the_conversation() -> None:
    ctx = lead_run_context(user_prompt="Use the experiment you recommended.")
    ctx.deps.state.domain.record_exchange(_RECOMMENDED)

    assert agent_deps_for(ctx.deps).exchanges == [_RECOMMENDED]


def test_the_sub_agent_reads_the_section_the_lead_reads() -> None:
    ctx = lead_run_context(user_prompt="Use the experiment you recommended.")
    ctx.deps.state.domain.record_exchange(_RECOMMENDED)

    rendered = pinned_conversation_so_far(run_context_for(agent_deps_for(ctx.deps)))

    assert rendered == exchanges_section([_RECOMMENDED])


_RESOLVED = (
    "A constraint that points at an earlier reply, such as the experiment you "
    "recommended or the third gene you listed, is written as what that reply "
    'named, read from "The conversation so far".'
)


def test_a_requirement_that_points_at_an_earlier_reply_names_its_referent() -> None:
    described = UserIntent.model_fields["explicit_constraints"].description or ""

    assert described.count(_RESOLVED) == 1


def test_frame_reads_such_a_requirement_as_what_the_reply_named() -> None:
    assert (
        'A requirement that points at an earlier reply means what "The '
        'conversation so far" shows that reply named.'
    ) in " ".join(_FRAME_INSTRUCTIONS.split())
