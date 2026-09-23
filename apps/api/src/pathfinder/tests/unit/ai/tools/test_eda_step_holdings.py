"""create_eda_step writes a step only for an analysis that selects genes."""

from __future__ import annotations

import json
from collections.abc import Callable, Coroutine, Sequence
from typing import Any

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.eda import EdaAnalysisDetail, EdaFilter

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_step
from pathfinder.domain.eda_parts import EdaEffectDirection
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.eda import gene_subset
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._eda_step_doubles import (
    COUNTS_ENTITY,
    CountedSubset,
    analysis_detail,
    bound,
    de_study,
    gene_filter,
    recording_commit,
    sample_filter,
    wire_gene_count,
)

Read = Callable[..., Coroutine[Any, Any, EdaAnalysisDetail]]


@pytest.fixture
def lead_ctx() -> RunContext[LeadDeps]:
    session = StrategySession(site_id="vectorbase")
    session.add_graph(StrategyGraph("g1", "Test", "vectorbase"))
    return lead_run_context(
        user_prompt="genes up at 24 h against 18 h and 36 h",
        strategy_session=session,
    )


def _reading(filters: Sequence[EdaFilter], *, with_computation: bool = False) -> Read:
    async def read(_site: str, *, analysis_id: str) -> EdaAnalysisDetail:
        del analysis_id
        return analysis_detail(with_computation=with_computation, filters=filters)

    return read


async def _no_commit(**kwargs: object) -> CommitResult:
    reason = f"no export may reach the commit: {sorted(kwargs)}"
    raise AssertionError(reason)


def _wire(
    monkeypatch: pytest.MonkeyPatch, read: Read, commit: object = _no_commit
) -> list[CountedSubset]:
    monkeypatch.setattr(eda_step, "bound_analysis", bound)
    monkeypatch.setattr(eda_step, "read_analysis", read)
    monkeypatch.setattr(eda_step, "apply_operations_and_commit", commit)
    counted = wire_gene_count(monkeypatch)
    monkeypatch.setattr(gene_subset, "get_study_detail_for_dataset", de_study)
    return counted


def _steps(ctx: RunContext[LeadDeps]) -> list[str]:
    graph = ctx.deps.runtime.strategy_session.get_graph(None)
    assert graph is not None
    return list(graph.steps)


async def test_a_sample_subset_with_no_computation_is_refused(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A subset of samples selects no gene, so it is never a step."""
    counted = _wire(monkeypatch, _reading([sample_filter(), sample_filter()]))

    with pytest.raises(ModelRetry) as refusal:
        await eda_step.create_eda_step(lead_ctx)

    assert str(refusal.value) == (
        "The open analysis holds 2 filters on Sample and 0 computations, and no "
        "filter on the gene entity pfal3D7 htseq counts (ENT_fd574cd6). A step "
        "exports genes, and a subset of another entity selects no genes, so "
        "nothing was written. Call run_eda_compute to run the comparison and "
        "export the genes that pass its thresholds, or call set_eda_filters "
        "with a filter on pfal3D7 htseq counts."
    )
    assert _steps(lead_ctx) == []
    assert counted == []


async def test_a_sample_subset_with_a_computation_but_no_thresholds_is_refused(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """With no thresholds the export is the subset, and the subset holds no gene."""
    _wire(monkeypatch, _reading([sample_filter()], with_computation=True))

    with pytest.raises(ModelRetry) as refusal:
        await eda_step.create_eda_step(lead_ctx)

    message = str(refusal.value)
    assert message.startswith(
        "The open analysis holds 1 filter on Sample and 1 computation, and no "
        "filter on the gene entity pfal3D7 htseq counts (ENT_fd574cd6)."
    )
    assert "send effect_size_threshold and significance_threshold" in message
    assert _steps(lead_ctx) == []


async def test_an_analysis_with_no_filter_and_no_computation_is_refused(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The empty analysis never reaches the graph as a step with an empty spec."""
    _wire(monkeypatch, _reading([]))

    with pytest.raises(ModelRetry) as refusal:
        await eda_step.create_eda_step(lead_ctx)

    assert str(refusal.value).startswith(
        "The open analysis holds no filter and 0 computations, and no filter on "
        "the gene entity pfal3D7 htseq counts (ENT_fd574cd6)."
    )
    assert _steps(lead_ctx) == []


async def test_a_sample_subset_with_a_computation_exports_the_volcano(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(
        monkeypatch,
        _reading([sample_filter()], with_computation=True),
        commit=recording_commit(applied),
    )

    answer = await eda_step.create_eda_step(
        lead_ctx, effect_size_threshold=1.0, significance_threshold=0.05
    )

    step = applied[0][0].step
    assert step.search_name == "GenesByEdaVizWithCompute"
    spec = json.loads(step.parameters["eda_analysis_spec"].value)
    assert len(spec["descriptor"]["computations"]) == 1
    assert returned(answer, eda_step.EdaStepCreated).step_id == step.id


async def test_a_gene_subset_with_no_computation_is_exported(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    counted = _wire(
        monkeypatch,
        _reading([sample_filter(), gene_filter()]),
        commit=recording_commit(applied),
    )

    await eda_step.create_eda_step(lead_ctx)

    step = applied[0][0].step
    assert step.search_name == "GenesByEdaSubset"
    spec = json.loads(step.parameters["eda_analysis_spec"].value)
    assert [f["entityId"] for f in spec["descriptor"]["subset"]["descriptor"]] == [
        "ENT_8151325d",
        COUNTS_ENTITY,
    ]
    assert [c.entity_id for c in counted] == [COUNTS_ENTITY]


@pytest.mark.parametrize("direction", ["upOnly", "downOnly", "upAndDown"])
async def test_a_direction_on_an_analysis_with_no_computation_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    lead_ctx: RunContext[LeadDeps],
    direction: EdaEffectDirection,
) -> None:
    """A direction selects a side of a comparison, and none has run."""
    _wire(monkeypatch, _reading([gene_filter()]))

    with pytest.raises(ModelRetry) as refusal:
        await eda_step.create_eda_step(lead_ctx, effect_direction=direction)

    assert str(refusal.value) == (
        f'effect_direction="{direction}" selects a side of a comparison, and the '
        f"open analysis holds 0 computations. Nothing was written. Call "
        f"run_eda_compute to run the comparison, then export with "
        f"effect_size_threshold, significance_threshold and effect_direction."
    )
    assert _steps(lead_ctx) == []


async def test_a_direction_with_no_thresholds_is_refused(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A direction with no volcano cut would export the subset and drop it."""
    _wire(monkeypatch, _reading([gene_filter()], with_computation=True))

    with pytest.raises(ModelRetry) as refusal:
        await eda_step.create_eda_step(lead_ctx, effect_direction="upOnly")

    assert str(refusal.value) == (
        'effect_direction="upOnly" selects a side of the volcano, so it needs '
        "effect_size_threshold and significance_threshold. Send both, or leave "
        "effect_direction unset to export the subset. Nothing was written."
    )
    assert _steps(lead_ctx) == []
