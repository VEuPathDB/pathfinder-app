"""create_eda_step chooses the search, writes the spec and attaches the step."""

from __future__ import annotations

import inspect
import json
from typing import Any

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import CombineOp, StrategyStepNode
from veupathdb.eda import EdaAnalysisDetail
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
from pathfinder.services.eda.gene_subset import GeneCount
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests._support.eda_step_doubles import (
    PHENOTYPE_GENES,
    CountedSubset,
    de_analysis,
    phenotype_subset,
    pushing_commit,
    recording_commit,
    sample_filter,
    unbound,
    wire_analysis,
    wire_gene_count,
)
from pathfinder.tests._support.eda_wire import (
    PHENOTYPE_DATASET,
    PHENOTYPE_ENTITY,
    PHENOTYPE_STUDY,
)
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
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


# A comparison of the RNA-Seq study's samples, which a compute export needs.
_COMPUTED = de_analysis(filters=[sample_filter()], with_computation=True)


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    detail: EdaAnalysisDetail,
    commit: object | None = None,
    genes: GeneCount = PHENOTYPE_GENES,
) -> list[CountedSubset]:
    wire_analysis(monkeypatch, eda_step, detail)
    counted = wire_gene_count(monkeypatch, genes=genes)
    if commit is not None:
        monkeypatch.setattr(eda_step, "apply_operations_and_commit", commit)
    return counted


async def test_a_subset_export_uses_the_generic_subset_search(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(monkeypatch, detail=phenotype_subset(), commit=recording_commit(applied))

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
        detail=_COMPUTED,
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


def test_the_export_takes_no_search_name() -> None:
    """The export writes the generic search of its kind and no other."""
    assert "search_name" not in inspect.signature(eda_step.create_eda_step).parameters


@pytest.mark.parametrize(
    ("detail", "significance", "search"),
    [
        (_COMPUTED, 0.05, "GenesByEdaVizWithCompute"),
        (phenotype_subset(), None, "GenesByEdaSubset"),
    ],
    ids=["a cut writes the compute search", "no cut writes the subset search"],
)
async def test_the_export_writes_the_search_its_cut_decides(
    monkeypatch: pytest.MonkeyPatch,
    lead_ctx: RunContext[LeadDeps],
    detail: EdaAnalysisDetail,
    significance: float | None,
    search: str,
) -> None:
    applied: list[Any] = []
    _wire(monkeypatch, detail=detail, commit=recording_commit(applied))

    await eda_step.create_eda_step(
        lead_ctx,
        effect_size_threshold=None if significance is None else 1.0,
        significance_threshold=significance,
    )

    assert [op.step.search_name for op in applied[0]] == [search]


async def test_the_thresholds_are_written_into_the_analysis_not_into_a_parameter(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The thresholds a user drags ARE the search parameters; they ride in the JSON."""
    applied: list[Any] = []
    _wire(
        monkeypatch,
        detail=_COMPUTED,
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
    _wire(monkeypatch, detail=phenotype_subset(), commit=recording_commit(applied))

    await eda_step.create_eda_step(lead_ctx, attach_to_step_id="s1", slot="secondary")

    attach = applied[0][0].attach
    assert attach.mode == "into-slot"
    assert attach.target_step_id == "s1"
    assert attach.slot == "secondary"


async def test_a_step_with_no_attach_point_becomes_a_new_root(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(monkeypatch, detail=phenotype_subset(), commit=recording_commit(applied))

    await eda_step.create_eda_step(lead_ctx)

    assert applied[0][0].attach.mode == "new-root"


async def test_a_compute_export_without_thresholds_raises_a_model_retry(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The plugin throws unless the volcano carries both thresholds."""
    _wire(monkeypatch, detail=_COMPUTED)

    with pytest.raises(ModelRetry) as excinfo:
        await eda_step.create_eda_step(lead_ctx, effect_size_threshold=1.0)

    assert "significance_threshold" in str(excinfo.value)


async def test_a_significance_threshold_alone_raises_a_model_retry(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The mirror of the pair guard: neither threshold may travel alone."""
    _wire(monkeypatch, detail=_COMPUTED)

    with pytest.raises(ModelRetry) as excinfo:
        await eda_step.create_eda_step(lead_ctx, significance_threshold=0.05)

    assert "effect_size_threshold" in str(excinfo.value)


async def test_a_compute_export_with_no_computation_names_the_compute_tool(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(monkeypatch, detail=phenotype_subset())

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
    _wire(monkeypatch, detail=phenotype_subset())

    with pytest.raises(ModelRetry) as excinfo:
        await eda_step.create_eda_step(lead_ctx, slot="secondary")

    assert "attach_to_step_id" in str(excinfo.value)


async def test_a_target_step_without_a_slot_raises_a_model_retry(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(monkeypatch, detail=phenotype_subset())

    with pytest.raises(ModelRetry) as excinfo:
        await eda_step.create_eda_step(lead_ctx, attach_to_step_id="s1")

    assert "slot" in str(excinfo.value)


async def test_a_session_with_no_graph_fails_loudly(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A turn always hydrates a graph, so its absence is a wiring fault."""
    _wire(monkeypatch, detail=phenotype_subset())
    lead_ctx.deps.runtime.strategy_session.graph = None

    with pytest.raises(ValidationError) as excinfo:
        await eda_step.create_eda_step(lead_ctx)

    assert excinfo.value.title == "No active strategy"
    assert excinfo.value.detail == (
        "The conversation holds no strategy to add the step to."
    )


def test_the_commit_context_carries_the_threads_original_request(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    """A later turn pushes under the request the thread answers, not its own."""
    lead_ctx.deps.state.domain.original_request = "genes up under heat shock"

    context = eda_step._strategy_context(lead_ctx, None, {})

    assert lead_ctx.deps.state.user_prompt == "export the febrile subset"
    assert context.user_prompt == "genes up under heat shock"


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

    spec = lead_ctx.deps.state.domain.operational_spec

    context = eda_step._strategy_context(lead_ctx, spec, {})

    assert context.stated_criteria == frozenset({"step_a", "step_b"})
    assert context.stated_structure == _TWO_STEP_STRUCTURE


def test_a_thread_that_framed_no_spec_states_no_criteria(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    assert eda_step._strategy_context(lead_ctx, None, {}).stated_criteria == frozenset()


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
        detail=phenotype_subset(),
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
    assert criterion.analysis is not None
    assert criterion.text == criterion.analysis.words
    assert criterion.analysis.words.startswith(
        "The genes of the analysis 'berghei subset'"
    )
    assert criterion.resolved_params == {}
    assert criterion.bound is True
    assert spec.goal == "febrile genes"
    assert spec.structure == SpecStructure(
        root=StructureNode(kind="leaf", criterion_id=result.step_id)
    )


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
        detail=phenotype_subset(),
        commit=pushing_commit(
            applied, session=ctx.deps.runtime.strategy_session, count=7
        ),
    )

    await eda_step.create_eda_step(ctx)

    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert [c.id for c in spec.criteria] == ["step_k1", "step_k2"]


async def test_an_export_the_site_did_not_take_still_marks_the_turn(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A detached export changed the canvas, so the turn wrote to the strategy."""

    async def unsynced_commit(*, deps: object, ops: list[Any]) -> CommitResult:
        del deps, ops
        return CommitResult(description="added a step")

    _wire(monkeypatch, detail=phenotype_subset(), commit=unsynced_commit)

    await eda_step.create_eda_step(lead_ctx)

    markers = lead_ctx.deps.state.turn_markers
    assert markers.built is False
    assert markers.edited is True
    assert markers.changed_strategy is True


async def test_an_export_the_site_took_records_the_build(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    applied: list[Any] = []
    _wire(
        monkeypatch,
        detail=phenotype_subset(),
        commit=pushing_commit(
            applied, session=lead_ctx.deps.runtime.strategy_session, count=132
        ),
    )

    await eda_step.create_eda_step(lead_ctx)

    markers = lead_ctx.deps.state.turn_markers
    assert markers.built is True
    assert markers.edited is True


async def test_a_subset_that_selects_no_genes_is_not_exported(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A sample-level filter selects samples; the step it would make holds no gene."""
    committed: list[object] = []

    async def commit(**kwargs: object) -> CommitResult:
        committed.append(kwargs)
        reason = "no export may reach the commit"
        raise AssertionError(reason)

    counted = _wire(
        monkeypatch,
        detail=phenotype_subset(),
        commit=commit,
        genes=GeneCount(count=0, unfiltered_count=PHENOTYPE_GENES.unfiltered_count),
    )

    with pytest.raises(ModelRetry) as refusal:
        await eda_step.create_eda_step(lead_ctx)

    whole = PHENOTYPE_GENES.unfiltered_count
    assert f"0 of the {whole:,} genes on Gene Phenotype Data" in str(refusal.value)
    assert "run_eda_compute" in str(refusal.value)
    assert committed == []
    assert [(c.study_id, c.entity_id) for c in counted] == [
        (PHENOTYPE_STUDY, PHENOTYPE_ENTITY),
    ]
    assert list(counted[0].filters) == phenotype_subset().descriptor.subset.descriptor
