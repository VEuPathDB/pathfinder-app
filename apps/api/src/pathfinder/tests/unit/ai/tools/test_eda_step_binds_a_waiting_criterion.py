"""``create_eda_step`` binds the criterion the spec holds waiting for it, where
the structure places it, and states every export by its binding."""

from __future__ import annotations

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_step
from pathfinder.ai.tools.standalone._eda_step_write import ExportJoin
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.tests._support.eda_step_doubles import (
    bound,
    read_detail,
    wire_gene_count,
)
from pathfinder.tests._support.eda_wire import PHENOTYPE_DATASET
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    combine,
    install_stub_api,
    leaf,
    session_with,
)
from pathfinder.tests.unit.ai.tools.conftest import summary_of
from pathfinder.tests.unit.domain.strategy._builders import shape

_WAITING = "c_essential"
_NO_STEP_TO_JOIN = f"The structure joins {_WAITING} to no step the strategy holds"
# The study names the species variable, so the words name it too.
_WORDS = "The genes of the analysis 'berghei subset': Species is one of P. berghei"


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


def _joined(operator: CombineOp, *inputs: StructureNode) -> StructureNode:
    return StructureNode(kind="combine", operator=operator, inputs=list(inputs))


def _under_the_root(operator: CombineOp = CombineOp.INTERSECT) -> StructureNode:
    return _joined(operator, _node("step_k1"), _node(_WAITING))


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
    assert exported.join == ExportJoin(
        combine_step_id=root.id,
        operator=CombineOp.INTERSECT,
        joined_step_id="step_k1",
        export_first=False,
    )
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
    assert _graph(ctx).words.analysis_kinds == {
        exported: StampedKind(search_name="GenesByEdaSubset", kind=AnalysisKind.SUBSET)
    }


@pytest.mark.parametrize(
    ("spec", "refusal"),
    [
        (_spec(_under_the_root()), "c_missing"),
        (_spec(_under_the_root(), dataset="DS_other"), "waits on dataset DS_other"),
        (
            _spec(_joined(CombineOp.INTERSECT, _node("step_k9"), _node(_WAITING))),
            f"{_NO_STEP_TO_JOIN}: it names ['{_WAITING}', 'step_k9'] and",
        ),
        (_spec(_node("step_k1")), f"{_NO_STEP_TO_JOIN}: it names ['step_k1'] and"),
    ],
    ids=[
        "an id the spec lacks",
        "another dataset",
        "no sibling the strategy holds",
        "a structure that does not place it",
    ],
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


async def test_a_place_inside_a_branch_joins_the_step_that_branch_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _ctx(session_with(combine("step_c1", leaf("step_k1"), leaf("step_k2")), {}))
    kinases, waiting = _spec(_node("step_k1")).criteria
    spec = OperationalSpec(
        goal="essential kinases",
        criteria=[kinases, kinases.model_copy(update={"id": "step_k2"}), waiting],
        structure=SpecStructure(
            root=_joined(
                CombineOp.INTERSECT,
                _node("step_k1"),
                _joined(CombineOp.UNION, _node("step_k2"), _node(_WAITING)),
            )
        ),
    )
    ctx.deps.state.domain.operational_spec = spec
    _wire(monkeypatch)

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
    stated = ctx.deps.state.domain.operational_spec
    assert stated is not None
    assert stated.structure == SpecStructure(
        root=_joined(
            CombineOp.INTERSECT,
            _node("step_k1"),
            _joined(CombineOp.UNION, _node("step_k2"), _node(exported.step_id)),
        )
    )
