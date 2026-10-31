"""create_eda_step names the kept side by its group."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import RunContext

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_step
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.eda_step_doubles import (
    DE_GENES,
    de_analysis,
    de_study,
    gene_filter,
    pushing_commit,
    recording_commit,
    sample_filter,
    wire_analysis,
    wire_gene_count,
)
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned

KEPT_UP = "Genes higher in 18h pbm, 36h pbm than in 24h pbm"


# A comparison of one reference group against two groups, and a gene filter,
# so the same analysis holds a compute export and a subset export.
_PBM = de_analysis(
    filters=[sample_filter(), gene_filter()],
    with_computation=True,
    group_a=["24h pbm"],
    group_b=["18h pbm", "36h pbm"],
)


def _session() -> StrategySession:
    session = StrategySession(site_id="vectorbase")
    session.add_graph(StrategyGraph("g1", "Test", "vectorbase"))
    return session


@pytest.fixture
def session() -> StrategySession:
    return _session()


@pytest.fixture
def lead_ctx(session: StrategySession) -> RunContext[LeadDeps]:
    return lead_run_context(
        user_prompt="genes higher at 24 hours", strategy_session=session
    )


def _wire(monkeypatch: pytest.MonkeyPatch, commit: object) -> None:
    wire_analysis(monkeypatch, eda_step, _PBM)
    monkeypatch.setattr(eda_step, "apply_operations_and_commit", commit)
    wire_gene_count(monkeypatch, study=de_study, genes=DE_GENES)


async def test_an_up_only_export_keeps_group_b(
    monkeypatch: pytest.MonkeyPatch,
    lead_ctx: RunContext[LeadDeps],
    session: StrategySession,
) -> None:
    applied: list[Any] = []
    _wire(monkeypatch, pushing_commit(applied, session=session, count=363))

    answer = await eda_step.create_eda_step(
        lead_ctx,
        effect_size_threshold=1.0,
        significance_threshold=0.05,
        effect_direction="upOnly",
    )

    result = returned(answer, eda_step.EdaStepCreated)
    assert result.selection == (
        "Kept 363 genes higher in 18h pbm, 36h pbm than in 24h pbm."
    )
    assert applied[0][0].step.display_name == KEPT_UP


async def test_the_step_is_named_by_the_direction(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(monkeypatch, recording_commit(applied))

    answer = await eda_step.create_eda_step(
        lead_ctx,
        effect_size_threshold=1.0,
        significance_threshold=0.05,
        effect_direction="downOnly",
    )

    assert applied[0][0].step.display_name == (
        "Genes higher in 24h pbm than in 18h pbm, 36h pbm"
    )
    result = returned(answer, eda_step.EdaStepCreated)
    assert result.selection == (
        "Keeps the genes higher in 24h pbm than in 18h pbm, 36h pbm."
    )


async def test_a_two_sided_export_keeps_both_sides(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(monkeypatch, recording_commit(applied))

    answer = await eda_step.create_eda_step(
        lead_ctx, effect_size_threshold=1.0, significance_threshold=0.05
    )

    assert returned(answer, eda_step.EdaStepCreated).selection == (
        "Keeps the genes that differ between 24h pbm and 18h pbm, 36h pbm."
    )


async def test_a_subset_export_states_no_selection(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(monkeypatch, recording_commit(applied))

    answer = await eda_step.create_eda_step(lead_ctx)

    assert returned(answer, eda_step.EdaStepCreated).selection is None
    assert applied[0][0].step.display_name == "heat shock subset"
