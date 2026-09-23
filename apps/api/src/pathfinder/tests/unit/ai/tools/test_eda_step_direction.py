"""create_eda_step names the kept side by its group and refuses a caption that disagrees."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.eda import EdaAnalysisDetail

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_step
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._eda_step_doubles import (
    analysis_detail,
    bound,
    pushing_commit,
    recording_commit,
    wire_gene_count,
)

KEPT_UP = "Genes higher in 18h pbm, 36h pbm than in 24h pbm"


async def _pbm_detail(_site: str, *, analysis_id: str) -> EdaAnalysisDetail:
    del analysis_id
    return analysis_detail(
        with_computation=True, group_a=["24h pbm"], group_b=["18h pbm", "36h pbm"]
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
    monkeypatch.setattr(eda_step, "bound_analysis", bound)
    monkeypatch.setattr(eda_step, "read_analysis", _pbm_detail)
    monkeypatch.setattr(eda_step, "apply_operations_and_commit", commit)
    wire_gene_count(monkeypatch)


async def test_a_caption_naming_only_the_reference_group_is_refused(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(monkeypatch, recording_commit(applied))

    with pytest.raises(ModelRetry) as refused:
        await eda_step.create_eda_step(
            lead_ctx,
            effect_size_threshold=1.0,
            significance_threshold=0.05,
            effect_direction="upOnly",
            caption="Genes higher in 24h pbm",
        )

    message = str(refused.value)
    assert '"Genes higher in 24h pbm"' in message
    assert KEPT_UP in message
    assert "downOnly" in message
    assert applied == []


async def test_a_caption_naming_the_kept_group_is_accepted(
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
        caption="Genes higher in 18h pbm and 36h pbm than in 24h pbm",
    )

    result = returned(answer, eda_step.EdaStepCreated)
    assert result.selection == (
        "Kept 363 genes higher in 18h pbm, 36h pbm than in 24h pbm."
    )
    assert applied[0][0].step.display_name == KEPT_UP


async def test_the_step_is_named_by_the_direction_not_by_the_caption(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(monkeypatch, recording_commit(applied))

    answer = await eda_step.create_eda_step(
        lead_ctx,
        effect_size_threshold=1.0,
        significance_threshold=0.05,
        effect_direction="downOnly",
        caption="Genes up at 24h pbm",
    )

    assert applied[0][0].step.display_name == (
        "Genes higher in 24h pbm than in 18h pbm, 36h pbm"
    )
    result = returned(answer, eda_step.EdaStepCreated)
    assert result.selection == (
        "Keeps the genes higher in 24h pbm than in 18h pbm, 36h pbm."
    )


async def test_a_caption_that_names_no_group_asks_for_one_and_suggests_no_direction(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(monkeypatch, recording_commit(applied))

    with pytest.raises(ModelRetry) as refused:
        await eda_step.create_eda_step(
            lead_ctx,
            effect_size_threshold=1.0,
            significance_threshold=0.05,
            effect_direction="upOnly",
            caption="Genes expressed higher at 24 hours than at 18 or 36 hours",
        )

    message = str(refused.value)
    assert "names no label of either group" in message
    assert "group A (24h pbm)" in message
    assert "group B (18h pbm, 36h pbm)" in message
    assert KEPT_UP in message
    assert "downOnly" not in message
    assert applied == []


async def test_a_one_sided_export_without_a_caption_is_refused(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(monkeypatch, recording_commit(applied))

    with pytest.raises(ModelRetry) as refused:
        await eda_step.create_eda_step(
            lead_ctx,
            effect_size_threshold=1.0,
            significance_threshold=0.05,
            effect_direction="upOnly",
        )

    message = str(refused.value)
    assert "needs a caption" in message
    assert "group A (24h pbm)" in message
    assert "group B (18h pbm, 36h pbm)" in message
    assert applied == []


async def test_a_two_sided_export_needs_no_caption(
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

    answer = await eda_step.create_eda_step(lead_ctx, caption="Any words at all")

    assert returned(answer, eda_step.EdaStepCreated).selection is None
    assert applied[0][0].step.display_name == "berghei subset"
