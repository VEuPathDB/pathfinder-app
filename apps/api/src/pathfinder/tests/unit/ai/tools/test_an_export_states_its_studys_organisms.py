"""The criterion an EDA export states carries the organisms of its study, so the
structure check scopes it like a bound dataset search."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import RunContext

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_step
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support import organism_reads
from pathfinder.tests._support.eda_step_doubles import (
    phenotype_subset,
    pushing_commit,
    wire_analysis,
    wire_gene_count,
)
from pathfinder.tests._support.eda_wire import PHENOTYPE_DATASET
from pathfinder.tests._support.run_context import lead_run_context

_PB = "Plasmodium berghei ANKA"


@pytest.fixture
def session() -> StrategySession:
    held = StrategySession(site_id="plasmodb")
    held.add_graph(StrategyGraph("g1", "Test", "plasmodb"))
    return held


@pytest.fixture
def lead_ctx(session: StrategySession) -> RunContext[LeadDeps]:
    return lead_run_context(
        user_prompt="export the berghei subset", strategy_session=session
    )


def _serve_the_study(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(organism_reads.STUDIES, PHENOTYPE_DATASET, [_PB])


async def test_the_exported_criterion_runs_on_its_studys_organisms(
    monkeypatch: pytest.MonkeyPatch,
    lead_ctx: RunContext[LeadDeps],
    session: StrategySession,
) -> None:
    _serve_the_study(monkeypatch)
    applied: list[Any] = []
    wire_analysis(monkeypatch, eda_step, phenotype_subset())
    wire_gene_count(monkeypatch)
    monkeypatch.setattr(
        eda_step,
        "apply_operations_and_commit",
        pushing_commit(applied, session=session, count=132),
    )

    await eda_step.create_eda_step(lead_ctx)

    spec = lead_ctx.deps.state.domain.operational_spec
    assert spec is not None
    step_id = applied[0][0].step.id
    assert [(c.id, c.dataset_organisms) for c in spec.criteria] == [(step_id, [_PB])]
