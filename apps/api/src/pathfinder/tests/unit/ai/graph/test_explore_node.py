from __future__ import annotations

import pytest
from assistant_core.graph.turn_state import PendingApproval
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.ui.vercel_ai.request_types import ToolApprovalResponded

from pathfinder.ai.lead.lead_memory_tools import ask_about_the_preferences
from pathfinder.ai.models.mock.explore_arc import (
    FIRST_LABEL,
    NO_READING,
    READINGS_REPLY,
    SECOND_LABEL,
)
from pathfinder.domain.modes import EXPLORE_PHASE
from pathfinder.domain.written_links import plain_markdown
from pathfinder.tests._support.recorded_counts import recorded_count
from pathfinder.tests.unit.ai.graph._explore_turns import (
    EXPLORE_PROMPT,
    GENE_TYPE_REPORT,
    NO_READING_PROMPT,
    PREFERENCE_PROMPT,
    ExploreDoubles,
    chunks_of,
    domain_of,
    explore_state,
    install_explore_doubles,
    run_explore,
    seed_count,
    update_of,
)


@pytest.fixture
def doubles(monkeypatch: pytest.MonkeyPatch) -> ExploreDoubles:
    return install_explore_doubles(monkeypatch)


async def test_an_explore_turn_ends_on_the_readings_card_for_the_lead(
    doubles: ExploreDoubles,
) -> None:
    command = await run_explore(explore_state(EXPLORE_PROMPT))

    park = update_of(command)["pending_approval"]
    shown = [t for t in doubles.types() if t in {"text-delta", "tool-approval-request"}]
    assert command.goto == "finalize_turn"
    assert (park.phase, park.tool_name) == ("lead", "consult_user")
    assert shown[-2:] == ["text-delta", "tool-approval-request"]
    assert "pending_durable_call" not in update_of(command)


async def test_the_card_reply_follows_the_facts(doubles: ExploreDoubles) -> None:
    await run_explore(explore_state(EXPLORE_PROMPT))

    types = doubles.types()
    assert types.index("data-facts") < types.index("text-delta")
    assert doubles.replies() == [plain_markdown(READINGS_REPLY)]
    assert types[0] == "data-turn-status"


async def test_an_explore_turn_writes_the_hand_over(doubles: ExploreDoubles) -> None:
    del doubles
    domain = domain_of(await run_explore(explore_state(EXPLORE_PROMPT)))

    assert domain.exchanges[-1].said == EXPLORE_PROMPT
    assert domain.exchanges[-1].card == (
        f"Readings offered: {FIRST_LABEL} ({seed_count()} genes); "
        f"{SECOND_LABEL} ({recorded_count(GENE_TYPE_REPORT)} genes)"
    )
    assert domain.exchanges[-1].reply == plain_markdown(READINGS_REPLY)
    assert domain.reading_labels() == [FIRST_LABEL, SECOND_LABEL]
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
    assert doubles.replies() == [plain_markdown(NO_READING)]
    assert domain_of(command).exchanges[-1].reply == plain_markdown(NO_READING)


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
    assert (park.phase, park.tool_name) == ("lead", "consult_user")
    assert domain_of(resumed).exchanges[-1].kind == "card_answer"
    assert domain_of(resumed).exchanges[-1].said == "yes"
    assert domain_of(resumed).reading_labels() == [FIRST_LABEL, SECOND_LABEL]
    assert doubles.replies()[-1] == plain_markdown(READINGS_REPLY)
