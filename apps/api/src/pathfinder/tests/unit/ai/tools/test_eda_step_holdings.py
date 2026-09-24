"""create_eda_step writes a step only for an analysis that selects genes."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.eda import EdaFilter

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_step
from pathfinder.domain.eda_parts import EdaEffectDirection
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests._support.eda_doubles import no_gene_study
from pathfinder.tests._support.eda_step_doubles import (
    COUNTS_ENTITY,
    DE_GENES,
    SAMPLE_ONLY_RETRY,
    CountedSubset,
    StudyReader,
    de_analysis,
    de_study,
    gene_filter,
    recording_commit,
    sample_filter,
    wire_analysis,
    wire_gene_count,
)
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned


@pytest.fixture
def lead_ctx() -> RunContext[LeadDeps]:
    session = StrategySession(site_id="vectorbase")
    session.add_graph(StrategyGraph("g1", "Test", "vectorbase"))
    return lead_run_context(
        user_prompt="genes up at 24 h against 18 h and 36 h",
        strategy_session=session,
    )


async def _no_commit(**kwargs: object) -> CommitResult:
    reason = f"no export may reach the commit: {sorted(kwargs)}"
    raise AssertionError(reason)


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    filters: Sequence[EdaFilter],
    *,
    with_computation: bool = False,
    commit: object = _no_commit,
    study: StudyReader = de_study,
) -> list[CountedSubset]:
    detail = de_analysis(filters=filters, with_computation=with_computation)
    wire_analysis(monkeypatch, eda_step, detail)
    monkeypatch.setattr(eda_step, "apply_operations_and_commit", commit)
    return wire_gene_count(monkeypatch, study=study, genes=DE_GENES)


def _steps(ctx: RunContext[LeadDeps]) -> list[str]:
    graph = ctx.deps.runtime.strategy_session.get_graph(None)
    assert graph is not None
    return list(graph.steps)


async def test_a_sample_subset_with_no_computation_is_refused(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A subset of samples selects no gene, so it is never a step."""
    counted = _wire(monkeypatch, [sample_filter()])

    with pytest.raises(ModelRetry) as refusal:
        await eda_step.create_eda_step(lead_ctx)

    assert str(refusal.value) == SAMPLE_ONLY_RETRY
    assert _steps(lead_ctx) == []
    assert counted == []


async def test_a_study_with_no_gene_entity_is_refused_and_writes_no_step(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    counted = _wire(monkeypatch, [sample_filter()], study=no_gene_study)

    with pytest.raises(ModelRetry) as refusal:
        await eda_step.create_eda_step(lead_ctx)

    assert str(refusal.value) == (
        "Study STUDY_53f554ec6a carries no VEUPATHDB_GENE_ID variable, so it "
        "cannot export a gene list to a strategy step. Nothing was written. "
        "Report the counts and the distributions instead."
    )
    assert _steps(lead_ctx) == []
    assert counted == []


async def test_a_sample_subset_with_a_computation_but_no_thresholds_is_refused(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """With no thresholds the export is the subset, and the subset holds no gene."""
    _wire(monkeypatch, [sample_filter()], with_computation=True)

    with pytest.raises(ModelRetry) as refusal:
        await eda_step.create_eda_step(lead_ctx)

    message = str(refusal.value)
    assert message.startswith(
        "The analysis holds 1 filter on Sample and 1 comparison, and no "
        "filter on pfal3D7 htseq counts."
    )
    assert "Send effect_size_threshold and significance_threshold" in message
    assert _steps(lead_ctx) == []


async def test_an_analysis_with_no_filter_and_no_computation_is_refused(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The empty analysis never reaches the graph as a step with an empty spec."""
    _wire(monkeypatch, [])

    with pytest.raises(ModelRetry) as refusal:
        await eda_step.create_eda_step(lead_ctx)

    assert str(refusal.value).startswith(
        "The analysis holds no filter and 0 comparisons, and no filter on "
        "pfal3D7 htseq counts."
    )
    assert _steps(lead_ctx) == []


async def test_a_sample_subset_with_a_computation_exports_the_volcano(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(
        monkeypatch,
        [sample_filter()],
        with_computation=True,
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
        [sample_filter(), gene_filter()],
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
    _wire(monkeypatch, [gene_filter()])

    with pytest.raises(ModelRetry) as refusal:
        await eda_step.create_eda_step(lead_ctx, effect_direction=direction)

    assert str(refusal.value) == (
        f'effect_direction="{direction}" selects a side of a comparison, and the '
        f"open analysis holds 0 comparisons. Nothing was written. Call "
        f"run_eda_compute to run the comparison, then export with "
        f"effect_size_threshold, significance_threshold and effect_direction."
    )
    assert _steps(lead_ctx) == []


async def test_a_direction_with_no_thresholds_is_refused(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A direction with no volcano cut would export the subset and drop it."""
    _wire(monkeypatch, [gene_filter()], with_computation=True)

    with pytest.raises(ModelRetry) as refusal:
        await eda_step.create_eda_step(lead_ctx, effect_direction="upOnly")

    assert str(refusal.value) == (
        'effect_direction="upOnly" selects a side of the volcano, so it needs '
        "effect_size_threshold and significance_threshold. Send both, or leave "
        "effect_direction unset to export the subset. Nothing was written."
    )
    assert _steps(lead_ctx) == []
