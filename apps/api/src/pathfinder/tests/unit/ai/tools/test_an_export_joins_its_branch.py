"""``create_eda_step`` joins an export to the built part of the smallest branch
that names its criterion, and leaves the structure as the spec states it."""

from __future__ import annotations

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaSubsetDescriptor,
)

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_step
from pathfinder.ai.tools.standalone._eda_step_write import ExportJoin
from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    criteria_under,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.eda.steps import EdaStepPlan
from pathfinder.tests._support.eda_wire import PHENOTYPE_DATASET
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    install_stub_api,
    session_with,
)
from pathfinder.tests.unit.ai.tools.conftest import summary_of
from pathfinder.tests.unit.domain.strategy._builders import (
    combine,
    leaf,
    shape,
    spec_joined,
    spec_leaf,
)

_WAITING = "c_essential"
_ESSENTIAL = (
    "c_essential_pkno",
    "c_essential_pf3d7",
    "c_essential_toxo",
    "c_essential_pberghei",
)
_NO_STEP_TO_JOIN = (
    f"The structure joins {_WAITING} to no step the strategy holds: it names "
    f"['{_WAITING}', 'step_k9'] and the strategy holds "
    f"['step_c1', 'step_c2', 'step_k1', 'step_k2', 'step_k3']. Nothing was "
    f"written. Dispatch edit_strategy so the structure places {_WAITING} beside "
    f"a step the strategy holds, then export again."
)
_NO_BRANCH_TO_JOIN = (
    f"The structure joins {_WAITING} to ['step_k2', 'step_k3'] as one branch, "
    f"and the strategy holds no step that joins exactly those. Nothing was "
    f"written. Dispatch edit_strategy so the strategy holds the structure's "
    f"branches, then export again."
)


async def _bound(_ctx: object) -> ConversationAnalysisView:
    return ConversationAnalysisView(
        site_id="plasmodb",
        dataset_id=PHENOTYPE_DATASET,
        analysis_id="t4fszEJ",
        revision=1,
    )


async def _read(_site: str, *, analysis_id: str) -> EdaAnalysisDetail:
    return EdaAnalysisDetail(
        analysis_id=analysis_id,
        display_name="berghei subset",
        study_id=PHENOTYPE_DATASET,
        num_filters=0,
        descriptor=EdaAnalysisDescriptor(subset=EdaSubsetDescriptor(descriptor=[])),
    )


async def _the_whole_subset(
    binding: ConversationAnalysisView, *_cut: object
) -> tuple[None, EdaStepPlan, None]:
    plan = EdaStepPlan(
        node=StrategyStepNode(search_name="GenesByEdaSubset"),
        is_compute_backed=False,
        binding=AnalysisBinding(
            dataset_id=binding.dataset_id, words="The genes of the analysis"
        ),
    )
    return None, plan, None


def _thread(
    monkeypatch: pytest.MonkeyPatch, held: StrategyStepNode, spec: OperationalSpec
) -> RunContext[LeadDeps]:
    """A thread that holds ``held`` and plans ``spec``, whose every export is
    the whole subset of one analysis on the phenotype dataset."""
    ctx = lead_run_context(
        user_prompt=spec.goal,
        strategy_session=session_with(held, {}),
        tool_call_id="c1",
    )
    ctx.deps.state.domain.operational_spec = spec
    install_stub_api(monkeypatch)
    monkeypatch.setattr(eda_step, "bound_analysis", _bound)
    monkeypatch.setattr(eda_step, "read_analysis", _read)
    monkeypatch.setattr(eda_step, "the_cut", _the_whole_subset)
    return ctx


def _graph(ctx: RunContext[LeadDeps]) -> StrategyGraph:
    graph = ctx.deps.runtime.strategy_session.graph
    assert graph is not None
    return graph


def _spec(root: StructureNode, *waiting: str) -> OperationalSpec:
    held = sorted(criteria_under(root) - set(waiting))
    return OperationalSpec(
        goal="essential transporters",
        criteria=[
            *(Criterion(id=c, text=c, search_name="geneById") for c in held),
            *(
                Criterion(
                    id=c, text=f"essential ({c})", needs_analysis_on=PHENOTYPE_DATASET
                )
                for c in waiting
            ),
        ],
        structure=SpecStructure(root=root),
    )


def _planned(*essential: str) -> StructureNode:
    return spec_joined(
        CombineOp.INTERSECT,
        spec_leaf("step_t1"),
        spec_joined(CombineOp.UNION, *(spec_leaf(c) for c in essential)),
    )


async def _exported(
    ctx: RunContext[LeadDeps], criterion_id: str
) -> eda_step.EdaStepCreated:
    answer = await eda_step.create_eda_step(ctx, criterion_id=criterion_id)
    return returned(answer, eda_step.EdaStepCreated)


async def test_four_exports_under_a_union_end_on_the_planned_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _thread(
        monkeypatch, leaf("step_t1"), _spec(_planned(*_ESSENTIAL), *_ESSENTIAL)
    )
    domain = ctx.deps.state.domain

    exported: list[eda_step.EdaStepCreated] = []
    shapes: list[str] = []
    answered: list[SpecStructure | None] = []
    for criterion_id in _ESSENTIAL:
        exported.append(await _exported(ctx, criterion_id))
        shapes.append(shape(_graph(ctx)))
        assert domain.answered_spec is not None
        answered.append(domain.answered_spec.structure)

    pkno, pf3d7, toxo, pberghei = (created.step_id for created in exported)
    assert shapes == [
        f"(step_t1 INTERSECT {pkno})",
        f"(step_t1 INTERSECT ({pkno} UNION {pf3d7}))",
        f"(step_t1 INTERSECT (({pkno} UNION {pf3d7}) UNION {toxo}))",
        f"(step_t1 INTERSECT ((({pkno} UNION {pf3d7}) UNION {toxo}) UNION {pberghei}))",
    ]
    assert answered == [
        SpecStructure(
            root=spec_joined(CombineOp.INTERSECT, spec_leaf("step_t1"), spec_leaf(pkno))
        ),
        SpecStructure(root=_planned(pkno, pf3d7)),
        SpecStructure(root=_planned(pkno, pf3d7, toxo)),
        SpecStructure(root=_planned(pkno, pf3d7, toxo, pberghei)),
    ]
    graph = _graph(ctx)
    first, second, third, fourth = (created.join for created in exported)
    assert first is not None
    assert second is not None
    assert third is not None
    assert graph.roots == {first.combine_step_id}
    union = graph.steps[first.combine_step_id].secondary_input_id
    assert [first, second, third, fourth] == [
        ExportJoin(
            combine_step_id=first.combine_step_id,
            operator=CombineOp.INTERSECT,
            joined_step_id="step_t1",
            export_first=False,
        ),
        ExportJoin(
            combine_step_id=second.combine_step_id,
            operator=CombineOp.UNION,
            joined_step_id=pkno,
            export_first=False,
        ),
        ExportJoin(
            combine_step_id=third.combine_step_id,
            operator=CombineOp.UNION,
            joined_step_id=second.combine_step_id,
            export_first=False,
        ),
        ExportJoin(
            combine_step_id=union or "",
            operator=CombineOp.UNION,
            joined_step_id=third.combine_step_id,
            export_first=False,
        ),
    ]
    spec = domain.operational_spec
    assert spec is not None
    assert spec.structure == SpecStructure(root=_planned(pkno, pf3d7, toxo, pberghei))
    assert [(c.id, c.text, c.needs_analysis_on) for c in spec.criteria] == [
        ("step_t1", "step_t1", None),
        *(
            (created.step_id, f"essential ({waiting})", None)
            for created, waiting in zip(exported, _ESSENTIAL, strict=True)
        ),
    ]
    assert domain.answered_spec == spec


async def test_the_exports_join_in_the_order_they_arrive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _thread(
        monkeypatch, leaf("step_t1"), _spec(_planned(*_ESSENTIAL), *_ESSENTIAL)
    )

    toxo = await _exported(ctx, "c_essential_toxo")
    pkno = await _exported(ctx, "c_essential_pkno")

    assert shape(_graph(ctx)) == (
        f"(step_t1 INTERSECT ({toxo.step_id} UNION {pkno.step_id}))"
    )
    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert spec.structure == SpecStructure(
        root=_planned(
            pkno.step_id, "c_essential_pf3d7", toxo.step_id, "c_essential_pberghei"
        )
    )


async def test_the_first_input_of_a_minus_is_the_first_input_of_its_combine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = spec_joined(CombineOp.MINUS, spec_leaf(_WAITING), spec_leaf("step_k1"))
    ctx = _thread(monkeypatch, leaf("step_k1"), _spec(plan, _WAITING))

    answer = await eda_step.create_eda_step(ctx, criterion_id=_WAITING)

    exported = returned(answer, eda_step.EdaStepCreated)
    graph = _graph(ctx)
    assert shape(graph) == f"({exported.step_id} MINUS step_k1)"
    assert exported.join == ExportJoin(
        combine_step_id=graph.primary_root_id() or "",
        operator=CombineOp.MINUS,
        joined_step_id="step_k1",
        export_first=True,
    )
    assert summary_of(answer).data["summary"] == (
        f"Step {exported.step_id} combined with step_k1 (MINUS), "
        f"{exported.step_id} first"
    )


async def test_a_join_below_the_root_keeps_the_root_and_names_the_joined_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = combine("step_c1", leaf("step_k1"), leaf("step_k2"))
    plan = spec_joined(
        CombineOp.INTERSECT,
        spec_leaf("step_k1"),
        spec_joined(CombineOp.UNION, spec_leaf("step_k2"), spec_leaf(_WAITING)),
    )
    ctx = _thread(monkeypatch, held, _spec(plan, _WAITING))

    answer = await eda_step.create_eda_step(ctx, criterion_id=_WAITING)

    exported = returned(answer, eda_step.EdaStepCreated)
    graph = _graph(ctx)
    assert graph.roots == {"step_c1"}
    assert shape(graph) == f"(step_k1 INTERSECT (step_k2 UNION {exported.step_id}))"
    assert exported.join == ExportJoin(
        combine_step_id=graph.steps["step_c1"].secondary_input_id or "",
        operator=CombineOp.UNION,
        joined_step_id="step_k2",
        export_first=False,
    )
    assert summary_of(answer).data["summary"] == (
        f"Step {exported.step_id} combined with step_k2 (UNION)"
    )


async def test_combine_with_root_joins_the_one_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = combine("step_c1", leaf("step_k1"), leaf("step_k2"))
    ctx = _thread(monkeypatch, held, _spec(spec_leaf("step_k1")))

    answer = await eda_step.create_eda_step(ctx, combine_with_root=CombineOp.MINUS)

    exported = returned(answer, eda_step.EdaStepCreated)
    graph = _graph(ctx)
    assert shape(graph) == (f"((step_k1 INTERSECT step_k2) MINUS {exported.step_id})")
    assert exported.join == ExportJoin(
        combine_step_id=graph.primary_root_id() or "",
        operator=CombineOp.MINUS,
        joined_step_id="step_c1",
        export_first=False,
    )
    assert summary_of(answer).data["summary"] == (
        f"Step {exported.step_id} combined with step_c1 (MINUS)"
    )


async def test_combine_with_root_needs_one_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _thread(monkeypatch, leaf("step_k1"), _spec(spec_leaf("step_k1")))
    graph = _graph(ctx)
    graph.steps.update(flatten_tree(leaf("step_loose")))
    graph.recompute_roots()

    with pytest.raises(ModelRetry) as raised:
        await eda_step.create_eda_step(ctx, combine_with_root=CombineOp.INTERSECT)

    assert "this strategy has 2: ['step_k1', 'step_loose']" in str(raised.value)
    assert sorted(graph.steps) == ["step_k1", "step_loose"]


@pytest.mark.parametrize(
    ("plan", "refusal"),
    [
        (
            spec_joined(CombineOp.INTERSECT, spec_leaf("step_k9"), spec_leaf(_WAITING)),
            _NO_STEP_TO_JOIN,
        ),
        (
            spec_joined(
                CombineOp.INTERSECT,
                spec_leaf("step_k1"),
                spec_joined(
                    CombineOp.UNION,
                    spec_leaf("step_k2"),
                    spec_leaf("step_k3"),
                    spec_leaf(_WAITING),
                ),
            ),
            _NO_BRANCH_TO_JOIN,
        ),
    ],
    ids=["no sibling the strategy holds", "a branch the strategy joins another way"],
)
async def test_a_place_the_strategy_does_not_hold_is_refused_and_nothing_written(
    monkeypatch: pytest.MonkeyPatch, plan: StructureNode, refusal: str
) -> None:
    held = combine(
        "step_c2",
        combine("step_c1", leaf("step_k1"), leaf("step_k2")),
        leaf("step_k3"),
        CombineOp.UNION,
    )
    spec = _spec(plan, _WAITING)
    ctx = _thread(monkeypatch, held, spec)

    with pytest.raises(ModelRetry) as raised:
        await eda_step.create_eda_step(ctx, criterion_id=_WAITING)

    assert str(raised.value) == refusal
    assert shape(_graph(ctx)) == "((step_k1 INTERSECT step_k2) UNION step_k3)"
    assert ctx.deps.state.domain.operational_spec == spec
