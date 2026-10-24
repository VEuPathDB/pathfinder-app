"""A requirement the framing pass dropped as met by a term of the bound expression
is named in the reply through its reference, which renders the term."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.clause_facts import MetClause
from pathfinder.domain.reply_references import render_reply
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.tests.unit.ai.lead._turn_contract_cases import kinds, reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_MET = MetClause(
    number="R2",
    requirement="in no other plant",
    clause="no protein in every genome outside FERN",
    criterion_id="c_ferns",
)
_RENDERED = (
    "'in no other plant' is met by the term the bound expression states: no "
    "protein in every genome outside FERN"
)


def _met(*clauses: MetClause) -> LeadDeps:
    state = pipeline_state(
        "orthomcl", user_prompt="Groups only in ferns.", user_message_id=uuid4()
    )
    state.turn_markers.met_clauses.extend(clauses)
    return lead_deps(state)


def test_the_reference_renders_the_term_that_meets_the_requirement() -> None:
    facts = TurnFacts(met_clauses=[_MET])

    assert render_reply("Also, [met:R2].", facts) == f"Also, {_RENDERED}."


def test_a_reply_that_does_not_name_the_met_clause_is_refused() -> None:
    assert "unnamed_clause" in kinds(_met(_MET), reply("The groups are built."))


def test_a_reply_that_names_the_met_clause_stands() -> None:
    found = kinds(_met(_MET), reply("The groups are built. [met:R2]."))

    assert "unnamed_clause" not in found


def test_a_turn_with_no_met_clause_asks_nothing() -> None:
    assert "unnamed_clause" not in kinds(_met(), reply("The groups are built."))


async def test_the_pass_carries_each_met_clause_to_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake(**kwargs: Any) -> FrameResult:
        return FrameResult(disposition="needs_user", met_by_clause=[_MET])

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)
    deps = lead_deps(pipeline_state("orthomcl", user_prompt="Groups only in ferns."))

    await run_frame(
        deps=deps,
        parent_tool_call_id="t1",
        work_order=frame_work_order("frame it", deps),
    )

    assert deps.state.turn_markers.met_clauses == [_MET]
