from __future__ import annotations

from strategist.ai.graph._lead_memory import MEMORY_NOT_READ, recalled
from strategist.ai.lead.lead_pins import pinned_turn_briefing
from strategist.domain.unread import Unread
from strategist.tests._support.run_context import run_context_for
from strategist.tests.unit.ai.lead._turn_contract_cases import (
    building_deps,
    kinds,
    reply,
)


def test_preferences_the_store_did_not_answer_are_named_once() -> None:
    deps = building_deps()
    domain = deps.state.domain

    held = recalled(Unread(reason="the memory store did not answer"), domain)

    assert (held, domain.turn_briefing) == (
        [],
        (
            "Your saved preferences were not read this turn (the memory store "
            "did not answer)."
        ),
    )
    assert MEMORY_NOT_READ in (pinned_turn_briefing(run_context_for(deps)) or "")


def test_the_line_raises_no_mismatch() -> None:
    deps = building_deps()
    recalled(Unread(reason="the memory store did not answer"), deps.state.domain)

    assert kinds(deps, reply("I added the step.")) == []
