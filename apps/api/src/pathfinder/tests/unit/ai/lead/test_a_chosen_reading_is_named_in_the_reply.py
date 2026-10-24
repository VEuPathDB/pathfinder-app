"""A framing pass that builds one reading of a request without asking marks the
reading it chose and the others, and the Lead's reply names each of them."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.chosen_reading import ChosenReading
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import kinds, reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_CHOSEN = ChosenReading(
    chosen="every lake on its own",
    alternatives=["the lakes pooled together"],
)


def _framed(chosen: ChosenReading | None) -> LeadDeps:
    state = pipeline_state(
        user_prompt="Find the reeds shared by the lakes.", user_message_id=uuid4()
    )
    if chosen is not None:
        state.turn_markers.chosen_readings.append(chosen)
    return lead_deps(state)


def test_a_chosen_reading_holds_at_least_one_other_reading() -> None:
    with pytest.raises(ValidationError):
        ChosenReading(chosen="every lake on its own", alternatives=[])


def test_a_reply_that_names_neither_reading_is_refused_with_both() -> None:
    deps = _framed(_CHOSEN)

    mismatches = reconcile(
        reply("Here are the shared reeds."), turn_record(run_context_for(deps))
    )

    assert [m.sentence for m in mismatches if m.kind == "unstated_reading"] == [
        (
            "The request reads more than one way, and the framing pass built "
            "'every lake on its own' without asking. Say in the reply which "
            "reading the strategy answers and name the other: 'the lakes pooled "
            "together'."
        )
    ]


def test_a_reply_that_names_only_the_chosen_reading_is_refused() -> None:
    deps = _framed(_CHOSEN)

    found = kinds(deps, reply("This counts every lake on its own."))

    assert "unstated_reading" in found


def test_a_reply_that_names_every_reading_stands() -> None:
    deps = _framed(_CHOSEN)
    prose = (
        "This counts every lake on its own; ask if you meant the lakes pooled "
        "together instead."
    )

    assert "unstated_reading" not in kinds(deps, reply(prose))


def test_a_turn_with_no_chosen_reading_asks_nothing() -> None:
    assert "unstated_reading" not in kinds(_framed(None), reply("Done."))


async def test_the_pass_marks_the_reading_it_chose_on_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake(**kwargs: Any) -> FrameResult:
        return FrameResult(disposition="needs_user", chosen_reading=_CHOSEN)

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)
    deps = lead_deps(pipeline_state(user_prompt="Find the reeds shared by the lakes."))

    result = await run_frame(
        deps=deps,
        parent_tool_call_id="t1",
        work_order=frame_work_order("frame it", deps),
    )

    assert isinstance(result, FrameResult)
    assert result.chosen_reading == _CHOSEN
    assert deps.state.turn_markers.chosen_readings == [_CHOSEN]
