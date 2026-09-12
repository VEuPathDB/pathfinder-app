"""create_eda_step chooses the search, writes the spec and attaches the step."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import CombineOp, StrategyStepNode
from veupathdb.errors import ValidationError

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_step
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.eda_wire import PHENOTYPE_DATASET
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._eda_step_doubles import (
    bound,
    pushing_commit,
    read_detail,
    read_detail_with_computation,
    recording_commit,
    unbound,
)
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    combine,
    leaf,
    session_with,
)

_TWO_STEP_STRUCTURE = SpecStructure(
    root=StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[
            StructureNode(kind="leaf", criterion_id="step_a"),
            StructureNode(kind="leaf", criterion_id="step_b"),
        ],
    ),
)


@pytest.fixture
def lead_ctx() -> RunContext[LeadDeps]:
    session = StrategySession(site_id="plasmodb")
    session.add_graph(StrategyGraph("g1", "Test", "plasmodb"))
    return lead_run_context(
        user_prompt="export the febrile subset", strategy_session=session
    )


def _wire(
    monkeypatch: pytest.MonkeyPatch, *, read: object, commit: object | None = None
) -> None:
    monkeypatch.setattr(eda_step, "bound_analysis", bound)
    monkeypatch.setattr(eda_step, "read_analysis", read)
    if commit is not None:
        monkeypatch.setattr(eda_step, "apply_operations_and_commit", commit)


async def test_a_subset_export_uses_the_generic_subset_search(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(monkeypatch, read=read_detail, commit=recording_commit(applied))

    answer = await eda_step.create_eda_step(lead_ctx)

    step = applied[0][0].step
    assert step.search_name == "GenesByEdaSubset"
    assert step.parameters["eda_dataset_id"].value == PHENOTYPE_DATASET
    spec = json.loads(step.parameters["eda_analysis_spec"].value)
    assert spec["studyId"] == PHENOTYPE_DATASET
    assert spec["descriptor"]["subset"]["descriptor"][0]["stringSet"] == ["P. berghei"]
    assert step.display_name == "berghei subset"
    result = returned(answer, eda_step.EdaStepCreated)
    assert result.search_name == "GenesByEdaSubset"
    assert result.is_compute_backed is False
    assert result.step_id == step.id
    assert "330423363" in result.guidance


async def test_a_compute_export_uses_the_viz_with_compute_search(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(
        monkeypatch,
        read=read_detail_with_computation,
        commit=recording_commit(applied),
    )

    answer = await eda_step.create_eda_step(
        lead_ctx,
        effect_size_threshold=1.0,
        significance_threshold=0.05,
    )

    step = applied[0][0].step
    assert step.search_name == "GenesByEdaVizWithCompute"
    spec = json.loads(step.parameters["eda_analysis_spec"].value)
    viz = spec["descriptor"]["computations"][0]["visualizations"][0]["descriptor"]
    assert viz["configuration"]["effectSizeThreshold"] == 1.0
    assert viz["configuration"]["significanceThreshold"] == 0.05
    assert viz["configuration"]["effectDirection"] == "upAndDown"
    result = returned(answer, eda_step.EdaStepCreated)
    assert result.search_name == "GenesByEdaVizWithCompute"
    assert result.is_compute_backed is True


async def test_an_explicit_search_name_wins_over_the_generic_one(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A per-dataset search already run by the researcher is still exportable."""
    applied: list[Any] = []
    _wire(monkeypatch, read=read_detail, commit=recording_commit(applied))

    await eda_step.create_eda_step(lead_ctx, search_name="GenesByRNASeqDESeq")

    assert applied[0][0].step.search_name == "GenesByRNASeqDESeq"


async def test_the_thresholds_are_written_into_the_analysis_not_into_a_parameter(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The thresholds a user drags ARE the search parameters; they ride in the JSON."""
    applied: list[Any] = []
    _wire(
        monkeypatch,
        read=read_detail_with_computation,
        commit=recording_commit(applied),
    )

    await eda_step.create_eda_step(
        lead_ctx, effect_size_threshold=2.0, significance_threshold=0.01
    )

    step = applied[0][0].step
    assert set(step.parameters) == {"eda_dataset_id", "eda_analysis_spec"}


async def test_attaching_into_a_slot_builds_the_slot_attach_point(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(monkeypatch, read=read_detail, commit=recording_commit(applied))

    await eda_step.create_eda_step(lead_ctx, attach_to_step_id="s1", slot="secondary")

    attach = applied[0][0].attach
    assert attach.mode == "into-slot"
    assert attach.target_step_id == "s1"
    assert attach.slot == "secondary"


async def test_a_step_with_no_attach_point_becomes_a_new_root(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(monkeypatch, read=read_detail, commit=recording_commit(applied))

    await eda_step.create_eda_step(lead_ctx)

    assert applied[0][0].attach.mode == "new-root"


async def test_a_compute_export_without_thresholds_raises_a_model_retry(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The plugin throws unless the volcano carries both thresholds."""
    _wire(monkeypatch, read=read_detail_with_computation)

    with pytest.raises(ModelRetry) as excinfo:
        await eda_step.create_eda_step(lead_ctx, effect_size_threshold=1.0)

    assert "significance_threshold" in str(excinfo.value)


async def test_a_significance_threshold_alone_raises_a_model_retry(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The mirror of the pair guard: neither threshold may travel alone."""
    _wire(monkeypatch, read=read_detail_with_computation)

    with pytest.raises(ModelRetry) as excinfo:
        await eda_step.create_eda_step(lead_ctx, significance_threshold=0.05)

    assert "effect_size_threshold" in str(excinfo.value)


async def test_a_compute_export_with_no_computation_names_the_compute_tool(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(monkeypatch, read=read_detail)

    with pytest.raises(ModelRetry) as excinfo:
        await eda_step.create_eda_step(
            lead_ctx, effect_size_threshold=1.0, significance_threshold=0.05
        )

    assert "run_eda_compute" in str(excinfo.value)


async def test_a_step_with_no_open_analysis_raises_a_model_retry(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    monkeypatch.setattr(eda_step, "bound_analysis", unbound)

    with pytest.raises(ModelRetry) as excinfo:
        await eda_step.create_eda_step(lead_ctx)

    assert "open_eda_analysis" in str(excinfo.value)


async def test_a_slot_without_a_target_step_raises_a_model_retry(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(monkeypatch, read=read_detail)

    with pytest.raises(ModelRetry) as excinfo:
        await eda_step.create_eda_step(lead_ctx, slot="secondary")

    assert "attach_to_step_id" in str(excinfo.value)


async def test_a_target_step_without_a_slot_raises_a_model_retry(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(monkeypatch, read=read_detail)

    with pytest.raises(ModelRetry) as excinfo:
        await eda_step.create_eda_step(lead_ctx, attach_to_step_id="s1")

    assert "slot" in str(excinfo.value)


async def test_a_session_with_no_graph_fails_loudly(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A turn always hydrates a graph, so its absence is a wiring fault."""
    _wire(monkeypatch, read=read_detail)
    lead_ctx.deps.runtime.strategy_session.graph = None

    with pytest.raises(ValidationError) as excinfo:
        await eda_step.create_eda_step(lead_ctx)

    assert "No active strategy graph" in str(excinfo.value)


def test_the_commit_context_carries_the_criteria_the_spec_states(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    """An EDA write reaches the commit path holding the same invariant."""
    lead_ctx.deps.state.domain.operational_spec = OperationalSpec(
        goal="febrile genes",
        criteria=[
            Criterion(id="step_a", text="febrile subset", search_name="GenesByTaxon"),
            Criterion(id="step_b", text="kinase domain", search_name="GenesByInterpro"),
        ],
        structure=_TWO_STEP_STRUCTURE,
    )

    context = eda_step._strategy_context(lead_ctx)

    assert context.stated_criteria == frozenset({"step_a", "step_b"})
    assert context.stated_structure == _TWO_STEP_STRUCTURE


def test_a_thread_that_framed_no_spec_states_no_criteria(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    assert eda_step._strategy_context(lead_ctx).stated_criteria == frozenset()


def _lead_ctx_over(root: StrategyStepNode) -> RunContext[LeadDeps]:
    """A Lead context whose session already holds a strategy."""
    session = session_with(root, {})
    return lead_run_context(
        user_prompt="export the febrile subset", strategy_session=session
    )


async def test_the_exported_step_becomes_a_criterion_of_the_spec(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A leaf wired into the main tree is a criterion like any other."""
    lead_ctx.deps.state.domain.operational_spec = OperationalSpec(goal="febrile genes")
    applied: list[Any] = []
    _wire(
        monkeypatch,
        read=read_detail,
        commit=pushing_commit(
            applied, session=lead_ctx.deps.runtime.strategy_session, count=132
        ),
    )

    answer = await eda_step.create_eda_step(lead_ctx)

    spec = lead_ctx.deps.state.domain.operational_spec
    assert spec is not None
    result = returned(answer, eda_step.EdaStepCreated)
    assert [c.id for c in spec.criteria] == [result.step_id]
    criterion = spec.criteria[0]
    assert criterion.search_name == "GenesByEdaSubset"
    assert criterion.text == "berghei subset"
    assert set(criterion.resolved_params) == {"eda_dataset_id", "eda_analysis_spec"}
    assert criterion.bound is True


async def test_a_step_outside_the_main_tree_states_no_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new root beside a larger tree is not what the strategy states."""
    ctx = _lead_ctx_over(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
    ctx.deps.state.domain.operational_spec = OperationalSpec(
        goal="febrile genes",
        criteria=[
            Criterion(id="step_k1", text="kinase domain", search_name="GenesByTaxon"),
            Criterion(id="step_k2", text="febrile subset", search_name="GenesByTaxon"),
        ],
    )
    applied: list[Any] = []
    _wire(
        monkeypatch,
        read=read_detail,
        commit=pushing_commit(
            applied, session=ctx.deps.runtime.strategy_session, count=7
        ),
    )

    await eda_step.create_eda_step(ctx)

    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert [c.id for c in spec.criteria] == ["step_k1", "step_k2"]


async def test_a_thread_that_framed_no_spec_records_nothing(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(
        monkeypatch,
        read=read_detail,
        commit=pushing_commit(
            applied, session=lead_ctx.deps.runtime.strategy_session, count=132
        ),
    )

    answer = await eda_step.create_eda_step(lead_ctx)

    graph = lead_ctx.deps.runtime.strategy_session.get_graph(None)
    assert graph is not None
    result = returned(answer, eda_step.EdaStepCreated)
    assert list(graph.steps) == [result.step_id]
    assert lead_ctx.deps.state.domain.operational_spec is None
