"""The run context a Lead-mounted tool is given in a unit test."""

from __future__ import annotations

import pytest

from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.run_context import lead_run_context


def test_it_carries_the_prompt_and_the_session_a_case_names() -> None:
    session = StrategySession(site_id="plasmodb")

    ctx = lead_run_context(user_prompt="find kinases here", strategy_session=session)

    assert ctx.deps.state.user_prompt == "find kinases here"
    assert ctx.deps.runtime.strategy_session is session


def test_the_turn_and_its_runtime_name_one_user() -> None:
    """A tool that reads the user id gets the same one from both sides."""
    ctx = lead_run_context()

    assert ctx.deps.runtime.user_id == ctx.deps.state.user_id


def test_no_database_stands_behind_it_by_default() -> None:
    ctx = lead_run_context()

    with pytest.raises(AssertionError, match="db factory should not be called"):
        ctx.deps.runtime.db_session_factory()
