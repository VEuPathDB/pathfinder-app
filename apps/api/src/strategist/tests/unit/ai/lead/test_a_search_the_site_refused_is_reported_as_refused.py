"""A search the site refused to run is reported as refused, never as missing:
qa.orthomcl.org answers 500 to MapProteinsByDiamond at its own defaults."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from pydantic_ai import RunContext
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ResolvedParams

from strategist.ai.agents.frame_result_checks import hold_the_reports_to_the_refusals
from strategist.ai.agents.state import AgentToolState, SearchOverview
from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead import frame_dispatch
from strategist.ai.lead.deltas import FrameResult
from strategist.ai.lead.dispatch_context import agent_deps_for
from strategist.ai.lead.frame_dispatch import run_frame
from strategist.ai.tools.standalone import _frame_count
from strategist.domain.strategy.constraints import ConstraintKind
from strategist.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
)
from strategist.tests._support.held_answers import let_through, said
from strategist.tests._support.run_context import run_context_for
from strategist.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)
from strategist.tests.unit.ai.tools.conftest import agent_run_context

_DIAMOND = "MapProteinsByDiamond"
_ANSWER = "HTTP 500: Internal Error"


def _refused(search: str = _DIAMOND) -> RequirementReport:
    return RequirementReport(
        requirement="R1",
        problem=RequirementProblem.SITE_REFUSED_THE_SEARCH,
        search=search,
    )


def _pass(*reports: RequirementReport) -> FrameResult:
    return FrameResult(
        disposition="needs_user",
        summary="The site refused the mapping search.",
        requirement_problems=list(reports),
    )


def _ctx(state: AgentToolState) -> RunContext[AgentDeps]:
    return agent_run_context(agent_state=state)


def test_a_refusal_naming_no_search_is_told_to_name_one() -> None:
    unnamed = _pass(
        RequirementReport(
            requirement="R1", problem=RequirementProblem.SITE_REFUSED_THE_SEARCH
        )
    )

    held = hold_the_reports_to_the_refusals(_ctx(AgentToolState()), unnamed)

    assert said(held) == [
        (
            "site_refused_the_search for R1 names no search: put the search the "
            "site refused in `search`, or report the requirement as "
            "site_has_no_search."
        )
    ]


def test_a_search_on_another_problem_is_dropped() -> None:
    report = RequirementReport(
        requirement="R1",
        problem=RequirementProblem.SITE_HAS_NO_SEARCH,
        search=_DIAMOND,
    )

    assert report.search == ""


async def test_a_count_the_site_refuses_is_recorded_for_the_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refusal = WDKError("Internal Error", status=500)

    async def _refuse(*_args: object) -> int:
        raise refusal

    monkeypatch.setattr(_frame_count, "count_bound_criterion", _refuse)
    state = AgentToolState()
    ctx = SimpleNamespace(deps=SimpleNamespace(site_id="orthomcl", agent_state=state))
    resolved = SimpleNamespace(open_slots=[], params={})
    definition = SimpleNamespace(allowed_primary_input_record_class_names=[])

    with pytest.raises(WDKError) as raised:
        await _frame_count.bound_count(
            cast("RunContext[AgentDeps]", ctx),
            cast("ResolvedParams", resolved),
            "sequence",
            _DIAMOND,
            cast("WDKSearch", definition),
        )

    assert raised.value is refusal
    assert state.refused_searches == {_DIAMOND: _ANSWER}


def test_no_search_after_a_refusal_is_sent_back() -> None:
    state = AgentToolState(refused_searches={_DIAMOND: _ANSWER})
    missing = _pass(
        RequirementReport(
            requirement="R1", problem=RequirementProblem.SITE_HAS_NO_SEARCH
        )
    )

    held = hold_the_reports_to_the_refusals(_ctx(state), missing)

    assert "site_refused_the_search" in " ".join(said(held))
    assert let_through(held, missing) == missing.with_gap(
        "missing_after_refusal",
        f"The pass reports a requirement no search answers after the site refused "
        f"{_DIAMOND} this turn.",
    )


def test_a_refusal_of_a_search_the_site_ran_is_sent_back() -> None:
    state = AgentToolState(refused_searches={_DIAMOND: _ANSWER})

    held = hold_the_reports_to_the_refusals(_ctx(state), _pass(_refused("ByBlast")))

    assert "ByBlast" in " ".join(said(held))


def test_a_refusal_report_when_the_site_refused_nothing_this_turn_is_sent_back() -> (
    None
):
    output = _pass(_refused("ByBlast"))

    held = hold_the_reports_to_the_refusals(_ctx(AgentToolState()), output)

    assert said(held) == [
        (
            "site_refused_the_search for R1 names ByBlast, and the site refused no "
            "search this turn. A requirement no search on this site answers is "
            "site_has_no_search."
        )
    ]
    assert let_through(held, output) == _pass().with_gap(
        "report_dropped",
        "The pass reported the site refused 'ByBlast' for R1, and it did not this "
        "turn.",
    )


def test_a_refusal_of_a_search_the_site_ran_is_told_the_searches_it_refused() -> None:
    state = AgentToolState(refused_searches={_DIAMOND: _ANSWER})

    held = hold_the_reports_to_the_refusals(_ctx(state), _pass(_refused("ByBlast")))

    assert said(held) == [
        (
            "site_refused_the_search for R1 names ByBlast, and this turn saw the "
            f"site refuse only {_DIAMOND}. Name one of those, or report the "
            "requirement as site_has_no_search."
        )
    ]


def test_a_refusal_report_let_through_is_dropped_with_its_gap() -> None:
    state = AgentToolState(refused_searches={_DIAMOND: _ANSWER})
    output = _pass(_refused("ByBlast"), _refused())

    held = hold_the_reports_to_the_refusals(_ctx(state), output)

    assert let_through(held, output) == _pass(_refused()).with_gap(
        "report_dropped",
        "The pass reported the site refused 'ByBlast' for R1, and it did not this "
        "turn.",
    )


def test_a_refusal_the_site_gave_passes() -> None:
    state = AgentToolState(refused_searches={_DIAMOND: _ANSWER})
    output = _pass(_refused())

    assert hold_the_reports_to_the_refusals(_ctx(state), output) == []


async def test_the_card_says_the_site_failed_and_offers_to_keep_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _stub(*, agent_deps: AgentDeps, **_kwargs: object) -> FrameResult:
        del agent_deps
        return _pass(_refused())

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _stub)
    deps = lead_deps(
        pipeline_state(
            user_prompt="Map these proteins to OrthoMCL groups with Diamond.",
            domain=StrategyDomainState(
                requirements=[
                    requirement(
                        ConstraintKind.UNTYPED, "search", "the map proteins search"
                    )
                ],
                discovered_searches={
                    _DIAMOND: SearchOverview(
                        search_name=_DIAMOND,
                        display_name="Map Proteins by Diamond",
                        record_type="sequence",
                        description="",
                        parameter_names=[],
                        required_params=[],
                    )
                },
            ),
        )
    )

    await run_frame(
        deps=deps, parent_tool_call_id="call_frame_1", work_order="map the proteins"
    )

    [question] = deps.state.domain.open_questions
    assert question.question == (
        "The site failed to run Map Proteins by Diamond. Keep "
        "'the map proteins search' to try again later, or drop it?"
    )
    assert [o.label for o in question.options] == [
        "Keep the map proteins search",
        "Drop the map proteins search",
    ]


def test_a_refusal_one_pass_saw_is_known_to_the_next_pass() -> None:
    deps = lead_deps(pipeline_state(user_prompt="genes with a diamond hit"))
    first = agent_deps_for(deps, call_id="call_frame_1")
    first.agent_state.refused_searches[_DIAMOND] = _ANSWER

    second = agent_deps_for(deps, call_id="call_frame_2")
    held = hold_the_reports_to_the_refusals(run_context_for(second), _pass(_refused()))

    assert (second.agent_state.refused_searches, held) == ({_DIAMOND: _ANSWER}, [])
