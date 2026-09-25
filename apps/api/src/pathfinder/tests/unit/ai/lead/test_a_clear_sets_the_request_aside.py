"""A clear sets the cleared strategy's request aside, and keeps the message's own."""

from __future__ import annotations

from uuid import uuid4

import pytest

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.answered_strategy import the_strategy_now_answers_to
from pathfinder.ai.lead.case_memory import collect_case_candidates
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.dispatch_context import agent_deps_for, framing_goal
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_tools import classify_user_intent, clear_strategy
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_budget import budget_stop_report
from pathfinder.ai.lead.verify_dispatch import verification_scope
from pathfinder.ai.tools.standalone import conversation
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.staleness import StaleBuild
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._answered_draft import QUESTION, framed
from pathfinder.tests.unit.ai.lead._budget_stop_turn import (
    BUDGET,
    TITLE,
    URL,
    built_outcome,
    built_session,
    hold_the_built_step,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_OLD = "surface vaccine candidates in P. falciparum 3D7"
_NEW = "Scrap it. Find transporters in P. berghei ANKA."
_OLD_ORGANISM = requirement(ConstraintKind.ORGANISM, "organism", "P. falciparum 3D7")
_NEW_ORGANISM = requirement(ConstraintKind.ORGANISM, "organism", "P. berghei ANKA")
_REBUILT = "step_transporters"


@pytest.fixture(autouse=True)
def _no_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _persisted(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        conversation, "persist_strategy_ast_to_conversation", _persisted
    )


async def _cleared() -> LeadDeps:
    """A built thread whose new message asks for another strategy and clears."""
    state = pipeline_state(
        user_prompt=_NEW,
        domain=StrategyDomainState(
            operational_spec=framed("signal peptide"),
            open_questions=[QUESTION],
            requirements=[_OLD_ORGANISM],
            recommendations=[_OLD_ORGANISM],
            original_request=_OLD,
            last_build_outcome=built_outcome(),
            stale_build=StaleBuild(changed_nodes=[("old_step", 70, 12)]),
        ),
    )
    state.user_message_id = uuid4()
    deps = lead_deps(state, strategy_session=built_session())
    classify_user_intent(
        run_context_for(deps, "t_classify"),
        UserIntent(
            classification=IntentClassification.NEW_STRATEGY,
            inferred_goal="transporters in P. berghei",
            explicit_constraints=[_NEW_ORGANISM],
        ),
    )
    await clear_strategy(
        run_context_for(deps, "t_clear"),
        confirm=True,
        reply="I will make this change and report what it takes with it.",
    )
    return deps


async def test_the_clear_keeps_only_the_request_of_this_message() -> None:
    domain = (await _cleared()).state.domain

    assert domain.operational_spec is None
    assert domain.open_questions == []
    assert domain.recommendations == []
    assert domain.last_build_outcome is None
    assert domain.stale_build is None
    assert domain.original_request == _NEW
    assert [c.requested_value for c in domain.requirements] == ["P. berghei ANKA"]


async def test_the_passes_after_a_clear_read_this_message_alone() -> None:
    deps = await _cleared()

    assert framing_goal(deps.state) == _NEW
    assert agent_deps_for(deps).user_prompt == _NEW
    assert verification_scope(deps, check_id="call_verify").messages == [_NEW]


async def test_a_budget_stop_after_a_clear_cites_no_cleared_link() -> None:
    deps = await _cleared()
    hold_the_built_step(deps.runtime.strategy_session, _REBUILT)
    deps.runtime.strategy_session.sync_state = None

    report = budget_stop_report(
        derive_ledger(deps.state, deps.intent),
        deps.runtime.strategy_session,
        deps.state.turn_markers,
        [],
    )

    assert URL not in report
    assert report.split("\n\n") == [
        f'The strategy holds 1 step; the final step is "{TITLE}".',
        "This turn changed the strategy and added no step.",
        "The strategy was not verified this turn.",
        BUDGET,
    ]


async def test_the_case_of_a_rebuild_after_a_clear_names_this_message() -> None:
    deps = await _cleared()
    state = deps.state
    hold_the_built_step(deps.runtime.strategy_session, _REBUILT)
    spec = OperationalSpec(
        goal=_NEW,
        criteria=[Criterion(id=_REBUILT, text="a transporter", search_name="S")],
    )
    state.domain.operational_spec = spec
    the_strategy_now_answers_to(
        state, spec, deps.runtime.strategy_session.get_graph(None)
    )
    state.record_build(BuildOutcome(pushed_step_ids=[_REBUILT], root_count=12))

    candidates = collect_case_candidates(state)

    assert [value.content["goal"] for value, _key in candidates] == [_NEW]


def test_a_new_build_supersedes_the_staleness_of_the_one_before() -> None:
    state = pipeline_state(
        user_prompt=_NEW,
        domain=StrategyDomainState(
            last_build_outcome=built_outcome(),
            stale_build=StaleBuild(changed_nodes=[("old_step", 70, 12)]),
        ),
    )

    state.record_build(BuildOutcome(pushed_step_ids=[_REBUILT], root_count=12))

    assert state.domain.stale_build is None
    assert "STALE:" not in derive_ledger(state, None).render_summary()
