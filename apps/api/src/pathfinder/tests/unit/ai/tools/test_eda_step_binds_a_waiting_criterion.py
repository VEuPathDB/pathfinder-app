"""``create_eda_step`` binds the criterion the spec holds waiting for it, where
the structure places it, and states every export by its binding."""

from __future__ import annotations

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_step
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.tests._support.eda_doubles import SPECIES_VARIABLE
from pathfinder.tests._support.eda_step_doubles import (
    bound,
    read_detail,
    wire_gene_count,
)
from pathfinder.tests._support.eda_wire import PHENOTYPE_DATASET
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    install_stub_api,
    leaf,
    session_with,
)

_WAITING = "c_essential"
_WORDS = f"The genes of the analysis 'berghei subset': {SPECIES_VARIABLE} is one of P. berghei"


def _ctx(session: StrategySession) -> RunContext[LeadDeps]:
    return lead_run_context(
        user_prompt="essential kinases", strategy_session=session, tool_call_id="c1"
    )


def _wire(monkeypatch: pytest.MonkeyPatch) -> None:
    install_stub_api(monkeypatch)
    monkeypatch.setattr(eda_step, "bound_analysis", bound)
    monkeypatch.setattr(eda_step, "read_analysis", read_detail)
    wire_gene_count(monkeypatch)


def _node(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _waiting(dataset: str = PHENOTYPE_DATASET) -> Criterion:
    return Criterion(
        id=_WAITING, text="essential in blood stages", needs_analysis_on=dataset
    )


def _spec(root: StructureNode, *, dataset: str = PHENOTYPE_DATASET) -> OperationalSpec:
    kinases = Criterion(id="step_k1", text="kinase domain", search_name="GenesByTaxon")
    return OperationalSpec(
        goal="essential kinases",
        criteria=[kinases, _waiting(dataset)],
        structure=SpecStructure(root=root),
    )


def _under_the_root(operator: CombineOp = CombineOp.INTERSECT) -> StructureNode:
    return StructureNode(
        kind="combine", operator=operator, inputs=[_node("step_k1"), _node(_WAITING)]
    )


def _graph(ctx: RunContext[LeadDeps]) -> StrategyGraph:
    graph = ctx.deps.runtime.strategy_session.graph
    assert graph is not None
    return graph


async def test_the_waiting_criterion_becomes_the_step_where_the_tree_puts_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _ctx(session_with(leaf("step_k1"), {}))
    ctx.deps.state.domain.operational_spec = _spec(_under_the_root())
    _wire(monkeypatch)

    answer = await eda_step.create_eda_step(ctx, criterion_id=_WAITING)

    exported = returned(answer, eda_step.EdaStepCreated)
    graph = _graph(ctx)
    root = graph.steps[graph.primary_root_id() or ""]
    assert root.operator is CombineOp.INTERSECT
    assert (root.primary_input_id, root.secondary_input_id) == (
        "step_k1",
        exported.step_id,
    )
    assert exported.combined_with_root is CombineOp.INTERSECT
    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert [c.id for c in spec.criteria] == ["step_k1", exported.step_id]
    criterion = spec.criteria[1]
    assert criterion.analysis is not None
    assert criterion.analysis.dataset_id == PHENOTYPE_DATASET
    assert criterion.analysis.words == _WORDS
    assert (criterion.needs_analysis_on, criterion.resolved_params) == (None, {})
    assert criterion.text == "essential in blood stages"
    assert spec.structure == SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.INTERSECT,
            inputs=[_node("step_k1"), _node(exported.step_id)],
        )
    )
    assert ctx.deps.state.domain.answered_spec == spec


async def test_an_export_with_no_spec_states_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The strategy answers to the export, so a spec states it."""
    session = StrategySession(site_id="plasmodb")
    session.add_graph(StrategyGraph("g1", "Test", "plasmodb"))
    ctx = _ctx(session)
    _wire(monkeypatch)

    answer = await eda_step.create_eda_step(ctx)

    exported = returned(answer, eda_step.EdaStepCreated).step_id
    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert spec.goal == "essential kinases"
    assert [(c.id, c.text) for c in spec.criteria] == [(exported, _WORDS)]
    assert spec.structure == SpecStructure(root=_node(exported))
    assert ctx.deps.state.domain.answered_spec == spec
    assert _graph(ctx).analysis_kinds == {
        exported: StampedKind(search_name="GenesByEdaSubset", kind=AnalysisKind.SUBSET)
    }


@pytest.mark.parametrize(
    ("spec", "refusal"),
    [
        (_spec(_under_the_root()), "c_missing"),
        (_spec(_under_the_root(), dataset="DS_other"), "waits on dataset DS_other"),
        (
            _spec(
                StructureNode(
                    kind="combine",
                    operator=CombineOp.INTERSECT,
                    inputs=[
                        StructureNode(
                            kind="combine",
                            operator=CombineOp.UNION,
                            inputs=[_node("step_k1"), _node(_WAITING)],
                        ),
                        _node("step_k1"),
                    ],
                )
            ),
            "not an input of the structure's root combine",
        ),
    ],
    ids=["an id the spec lacks", "another dataset", "a place inside a branch"],
)
async def test_a_criterion_the_export_cannot_take_is_refused_and_nothing_written(
    monkeypatch: pytest.MonkeyPatch, spec: OperationalSpec, refusal: str
) -> None:
    ctx = _ctx(session_with(leaf("step_k1"), {}))
    ctx.deps.state.domain.operational_spec = spec
    _wire(monkeypatch)
    criterion_id = "c_missing" if refusal == "c_missing" else _WAITING

    with pytest.raises(ModelRetry) as raised:
        await eda_step.create_eda_step(ctx, criterion_id=criterion_id)

    assert refusal in str(raised.value)
    assert sorted(_graph(ctx).steps) == ["step_k1"]
    assert ctx.deps.state.domain.operational_spec == spec


async def test_the_structure_is_the_whole_placement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _ctx(session_with(leaf("step_k1"), {}))
    ctx.deps.state.domain.operational_spec = _spec(_under_the_root())
    _wire(monkeypatch)

    with pytest.raises(ModelRetry) as raised:
        await eda_step.create_eda_step(
            ctx, criterion_id=_WAITING, combine_with_root=CombineOp.UNION
        )

    assert "the structure places" in str(raised.value)
    assert sorted(_graph(ctx).steps) == ["step_k1"]


async def test_an_export_on_a_dataset_a_criterion_waits_on_names_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The handoff is by id, so an export that names none is refused."""
    ctx = _ctx(session_with(leaf("step_k1"), {}))
    ctx.deps.state.domain.operational_spec = _spec(_under_the_root())
    _wire(monkeypatch)

    with pytest.raises(ModelRetry) as raised:
        await eda_step.create_eda_step(ctx, combine_with_root=CombineOp.INTERSECT)

    assert f'criterion_id="{_WAITING}"' in str(raised.value)
    assert sorted(_graph(ctx).steps) == ["step_k1"]


async def test_the_first_export_of_a_spec_that_only_waits_is_the_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = StrategySession(site_id="plasmodb")
    session.add_graph(StrategyGraph("g1", "Test", "plasmodb"))
    ctx = _ctx(session)
    ctx.deps.state.domain.operational_spec = OperationalSpec(
        goal="essential genes",
        criteria=[_waiting()],
        structure=SpecStructure(root=_node(_WAITING)),
    )
    _wire(monkeypatch)

    answer = await eda_step.create_eda_step(ctx, criterion_id=_WAITING)

    exported = returned(answer, eda_step.EdaStepCreated).step_id
    assert _graph(ctx).roots == {exported}
    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert spec.structure == SpecStructure(root=_node(exported))
