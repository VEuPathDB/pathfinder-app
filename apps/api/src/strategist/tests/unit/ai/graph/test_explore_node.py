from __future__ import annotations

import pytest
from assistant_core.graph.turn_state import PendingApproval
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.ui.vercel_ai.request_types import ToolApprovalResponded

from strategist.ai.lead.lead_memory_tools import ask_about_the_preferences
from strategist.ai.models.mock.explore_arc import (
    NO_READING,
    ONE_READING,
    READINGS_REPLY,
)
from strategist.domain.modes import EXPLORE_PHASE, READINGS_PHASE
from strategist.tests._support.explore_turns import (
    EXPLORE_PROMPT,
    FIRST_PLAN,
    FIRST_READING,
    GENE_TYPE_REPORT,
    NO_READING_PROMPT,
    ONE_READING_PROMPT,
    PREFERENCE_PROMPT,
    SECOND_READING,
    SIGNAL_PEPTIDE_REPORT,
    ExploreDoubles,
    chunks_of,
    domain_of,
    explore_state,
    install_explore_doubles,
    run_explore,
    update_of,
)
from strategist.tests._support.recorded_counts import recorded_count


@pytest.fixture
def doubles(monkeypatch: pytest.MonkeyPatch) -> ExploreDoubles:
    return install_explore_doubles(monkeypatch)


async def test_an_explore_turn_parks_the_readings_card_under_the_readings_phase(
    doubles: ExploreDoubles,
) -> None:
    command = await run_explore(explore_state(EXPLORE_PROMPT))

    park = update_of(command)["pending_approval"]
    shown = [t for t in doubles.types() if t in {"text-delta", "tool-approval-request"}]
    assert command.goto == "finalize_turn"
    assert (park.phase, park.tool_name) == (READINGS_PHASE, "consult_user")
    assert shown[-2:] == ["text-delta", "tool-approval-request"]
    assert "pending_durable_call" not in update_of(command)


async def test_the_card_reply_follows_the_facts(doubles: ExploreDoubles) -> None:
    await run_explore(explore_state(EXPLORE_PROMPT))

    types = doubles.types()
    assert types.index("data-facts") < types.index("text-delta")
    assert doubles.replies() == [READINGS_REPLY]
    assert types[0] == "data-turn-status"


async def test_an_explore_turn_writes_the_hand_over(doubles: ExploreDoubles) -> None:
    del doubles
    domain = domain_of(await run_explore(explore_state(EXPLORE_PROMPT)))

    assert domain.exchanges[-1].said == EXPLORE_PROMPT
    assert domain.exchanges[-1].card == (
        f"Readings offered: {FIRST_READING} ({recorded_count(SIGNAL_PEPTIDE_REPORT)} genes); "
        f"{SECOND_READING} ({recorded_count(GENE_TYPE_REPORT)} genes)"
    )
    assert domain.exchanges[-1].reply == READINGS_REPLY
    assert domain.reading_labels() == [FIRST_READING, SECOND_READING]
    assert EXPLORE_PROMPT in domain.request_messages
    assert domain.requirements == []
    assert domain.operational_spec is None
    assert domain.original_request == ""


async def test_a_turn_with_no_buildable_reading_parks_nothing(
    doubles: ExploreDoubles,
) -> None:
    command = await run_explore(explore_state(NO_READING_PROMPT))

    assert "pending_approval" not in update_of(command)
    assert domain_of(command).named_readings == []
    assert doubles.replies() == [NO_READING]
    assert domain_of(command).exchanges[-1].reply == NO_READING


async def test_a_stated_preference_parks_for_explore_with_its_question(
    doubles: ExploreDoubles,
) -> None:
    command = await run_explore(explore_state(PREFERENCE_PROMPT))

    park = update_of(command)["pending_approval"]
    lead_wrote: list[object] = []
    ask_about_the_preferences(
        DeferredToolRequests(
            approvals=[
                ToolCallPart("remember", park.tool_args, tool_call_id=park.tool_call_id)
            ]
        ),
        lead_wrote.append,
    )
    assert (park.phase, park.tool_name) == (EXPLORE_PHASE, "remember")
    assert doubles.of_type("data-tool-summary")[-1:] == chunks_of(lead_wrote)
    assert chunks_of(lead_wrote)[0]["data"]["summary"].startswith(
        "Remember in your later conversations: stated preference:"
    )
    assert domain_of(command).exchanges[-1].card == "approve remember"
    assert domain_of(command).named_readings == []


async def test_an_answered_preference_resumes_explore_to_the_readings_card(
    doubles: ExploreDoubles,
) -> None:
    first = explore_state(PREFERENCE_PROMPT)
    parked = await run_explore(first)
    card: PendingApproval = update_of(parked)["pending_approval"]
    answered = first.model_copy(
        update={
            "domain": domain_of(parked),
            "pending_approval": card,
            "approval_responses": {
                card.tool_call_id: ToolApprovalResponded(id="a-1", approved=True)
            },
        }
    )

    resumed = await run_explore(answered)

    park = update_of(resumed)["pending_approval"]
    assert (park.phase, park.tool_name) == (READINGS_PHASE, "consult_user")
    assert domain_of(resumed).exchanges[-1].kind == "card_answer"
    assert domain_of(resumed).exchanges[-1].said == "yes"
    assert domain_of(resumed).reading_labels() == [FIRST_READING, SECOND_READING]
    assert doubles.replies()[-1] == READINGS_REPLY


async def test_one_buildable_reading_is_counted_and_offered_to_build(
    doubles: ExploreDoubles,
) -> None:
    command = await run_explore(explore_state(ONE_READING_PROMPT))

    [facts] = doubles.of_type("data-facts")
    [comparison] = facts["data"]["comparisons"]
    assert [(v["label"], v["geneCount"]) for v in comparison["variants"]] == [
        (FIRST_READING, recorded_count(SIGNAL_PEPTIDE_REPORT))
    ]
    assert "pending_approval" not in update_of(command)
    assert doubles.of_type("tool-approval-request") == []
    assert doubles.replies() == [ONE_READING]
    assert domain_of(command).named_readings == []
    assert domain_of(command).exchanges[-1].card == ""
    assert [c["data"] for c in doubles.of_type("data-build-offer")] == [
        {
            "label": FIRST_READING,
            "plan": FIRST_PLAN,
            "geneCount": recorded_count(SIGNAL_PEPTIDE_REPORT),
            "also": "",
        }
    ]


async def test_a_turn_that_offers_the_readings_card_offers_no_build(
    doubles: ExploreDoubles,
) -> None:
    await run_explore(explore_state(EXPLORE_PROMPT))

    assert doubles.of_type("data-build-offer") == []


async def test_a_turn_with_no_reading_offers_no_build(doubles: ExploreDoubles) -> None:
    await run_explore(explore_state(NO_READING_PROMPT))

    assert doubles.of_type("data-build-offer") == []


async def test_a_fresh_explore_turn_leaves_its_mark_to_the_route_node(
    doubles: ExploreDoubles,
) -> None:
    await run_explore(explore_state(NO_READING_PROMPT))

    assert doubles.of_type("data-turn-route") == []


async def test_an_answered_explore_card_marks_its_reply_explore(
    doubles: ExploreDoubles,
) -> None:
    first = explore_state(PREFERENCE_PROMPT)
    parked = await run_explore(first)
    card: PendingApproval = update_of(parked)["pending_approval"]
    answered = first.model_copy(
        update={
            "domain": domain_of(parked),
            "pending_approval": card,
            "approval_responses": {
                card.tool_call_id: ToolApprovalResponded(id="a-1", approved=True)
            },
        }
    )

    await run_explore(answered)

    assert [c["data"]["route"] for c in doubles.of_type("data-turn-route")] == [
        "explore"
    ]
