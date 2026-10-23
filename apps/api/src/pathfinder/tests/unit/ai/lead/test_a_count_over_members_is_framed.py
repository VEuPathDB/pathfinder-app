from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb_mcp import catalog

from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.intent_gate import tools_the_turn_offers
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import search_reads
from pathfinder.ai.tools.standalone.column_tally import count_by_column
from pathfinder.ai.tools.standalone.search_reads import count_search
from pathfinder.services.experiment.variant_comparison import VariantInput
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
    user_intent,
)

_ASKED = "Which values of the column hold the most records of the result?"
_GUESSED = VariantInput(label="the records", search_name="NoSuchSearch", parameters={})
_UNLISTED = (
    "orthomcl lists no search NoSuchSearch (the records). The catalog lookup for "
    "'No Such Search' finds no search, so orthomcl has no search of that name."
)
_REROUTE = (
    "This conversation holds no strategy, and framing finds the searches: with "
    "the message classified new_strategy, dispatch frame_problem with the "
    "request, and count the built step with count_step_by_column."
)


@pytest.fixture(autouse=True)
def _no_such_search(monkeypatch: pytest.MonkeyPatch) -> None:
    async def unlisted(_site_id: str, _names: list[str]) -> dict[str, str]:
        return {}

    async def nothing(*_args: object, **_kwargs: object) -> list[object]:
        return []

    monkeypatch.setattr(search_reads, "search_record_types", unlisted)
    monkeypatch.setattr(catalog, "search_for_searches", nothing)


def _question_turn(*, with_a_step: bool = False) -> LeadDeps:
    state = pipeline_state("orthomcl", user_prompt=_ASKED)
    session = session_with_one_step("orthomcl") if with_a_step else None
    deps = lead_deps(
        state,
        intent=user_intent(IntentClassification.FOLLOW_UP_QUESTION),
        strategy_session=session,
    )
    state.turn_markers.intent_classified = True
    return deps


async def _tally_refusal(deps: LeadDeps) -> str:
    with pytest.raises(ModelRetry) as refused:
        await count_by_column(
            run_context_for(deps), _GUESSED, record_type="group", column="organism"
        )
    return str(refused.value)


async def test_a_tally_of_a_search_the_catalog_lacks_is_sent_to_framing() -> None:
    assert await _tally_refusal(_question_turn()) == f"{_UNLISTED} {_REROUTE}"


async def test_a_conversation_with_a_step_is_not_sent_to_framing() -> None:
    assert await _tally_refusal(_question_turn(with_a_step=True)) == _UNLISTED


async def test_a_turn_that_framed_is_not_pointed_at_framing_again() -> None:
    deps = _question_turn()
    deps.state.turn_markers.framed = True

    assert await _tally_refusal(deps) == _UNLISTED


async def test_a_count_of_a_search_the_catalog_lacks_is_not_sent_to_framing() -> None:
    with pytest.raises(ModelRetry) as refused:
        await count_search(run_context_for(_question_turn()), _GUESSED)

    assert str(refused.value) == _UNLISTED


async def test_the_first_message_reclassified_reaches_frame() -> None:
    deps = _question_turn()
    await _tally_refusal(deps)
    assert "frame_problem" not in tools_the_turn_offers(deps, ["frame_problem"])

    await classify_user_intent(
        run_context_for(deps, tool_call_id="call_reclassify"),
        user_intent(IntentClassification.NEW_STRATEGY),
    )

    assert tools_the_turn_offers(deps, ["frame_problem", "count_step_by_column"]) == {
        "frame_problem",
        "count_step_by_column",
    }
