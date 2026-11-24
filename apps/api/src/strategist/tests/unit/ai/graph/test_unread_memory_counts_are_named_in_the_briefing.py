from __future__ import annotations

from strategist.ai.graph._lead_memory import indexed
from strategist.domain.unread import Unread
from strategist.tests.unit.ai.lead._turn_contract_cases import building_deps


def test_memory_counts_the_store_did_not_answer_are_named_once() -> None:
    domain = building_deps().state.domain

    counted = indexed(Unread(reason="the memory store did not answer"), domain)

    assert (counted, domain.turn_briefing) == (
        {},
        (
            "Your other saved memories were not counted this turn (the memory "
            "store did not answer); search_memory still reads them."
        ),
    )


def test_counted_memories_add_no_line() -> None:
    domain = building_deps().state.domain

    counted = indexed({"case": 2}, domain)

    assert (counted, domain.turn_briefing) == ({"case": 2}, "")
