from __future__ import annotations

from strategist.ai.explore.explore_agent import pinned_unreadable_strategy
from strategist.domain.strategy.session import StrategySession
from strategist.domain.unread import Unread
from strategist.tests._support.run_context import run_context_for
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


def test_explore_is_told_the_stored_plan_is_unreadable() -> None:
    session = StrategySession("plasmodb")
    session.unreadable = Unread(reason="root: a combine names one step twice")
    deps = lead_deps(pipeline_state("plasmodb"), strategy_session=session)

    assert pinned_unreadable_strategy(run_context_for(deps)) == (
        "The stored strategy of this conversation could not be read, so it is "
        "shown as unreadable and no step of it can be read or built on: root: a "
        "combine names one step twice"
    )


def test_a_readable_plan_adds_no_line() -> None:
    deps = lead_deps(pipeline_state("plasmodb"))

    assert [pinned_unreadable_strategy(run_context_for(deps))] == [None]
