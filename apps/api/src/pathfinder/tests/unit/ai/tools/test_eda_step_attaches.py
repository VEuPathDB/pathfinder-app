"""The spec's structure after ``create_eda_step`` attaches, not replaces."""

from __future__ import annotations

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_step
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    DroppedCriterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    eda_backed_drops,
    structure_criteria,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_hydration import spec_from_ast
from pathfinder.tests._support.eda_wire import PHENOTYPE_DATASET
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._eda_step_doubles import (
    bound,
    read_detail,
    wire_gene_count,
)
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    combine,
    install_stub_api,
    leaf,
    session_with,
)
from pathfinder.tests.unit.ai.tools.conftest import summary_of

_GOAL = "essential kinases"


def _wire(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eda_step, "bound_analysis", bound)
    monkeypatch.setattr(eda_step, "read_analysis", read_detail)
    wire_gene_count(monkeypatch)


def _lead_ctx_over(root: StrategyStepNode) -> RunContext[LeadDeps]:
    return lead_run_context(
        user_prompt="export the berghei subset",
        strategy_session=session_with(root, {}),
        tool_call_id="call_export",
    )


def _graph(ctx: RunContext[LeadDeps]) -> StrategyGraph:
    graph = ctx.deps.runtime.strategy_session.graph
    assert graph is not None
    return graph


def _reference(graph: StrategyGraph) -> OperationalSpec:
    """The spec the build would state for the strategy the graph now holds."""
    ast = graph.to_strategy_ast()
    assert ast is not None
    return spec_from_ast(ast, goal=_GOAL)


async def test_an_export_into_a_free_slot_takes_that_slot_in_the_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_stub_api(monkeypatch)
    ctx = _lead_ctx_over(
        StrategyStepNode(
            id="step_c1",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=leaf("step_k1"),
        ),
    )
    ctx.deps.state.domain.operational_spec = OperationalSpec(
        goal=_GOAL,
        criteria=[
            Criterion(id="step_k1", text="kinase domain", search_name="GenesByTaxon")
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="step_k1"),
        ),
    )
    _wire(monkeypatch)

    answer = await eda_step.create_eda_step(
        ctx, attach_to_step_id="step_c1", slot="secondary"
    )

    exported = returned(answer, eda_step.EdaStepCreated).step_id
    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert spec.structure == _reference(_graph(ctx)).structure
    assert structure_criteria(spec.structure) == {"step_k1", exported}
    assert spec.structure is not None
    assert spec.structure.root.operator is CombineOp.INTERSECT
    assert [c.id for c in spec.criteria] == ["step_k1", exported]


async def test_an_export_makes_the_strategy_answer_to_the_spec_that_states_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The export is the thread's own write, so the answer moves with it."""
    install_stub_api(monkeypatch)
    ctx = _lead_ctx_over(
        StrategyStepNode(
            id="step_c1",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=leaf("step_k1"),
        ),
    )
    ctx.deps.state.domain.operational_spec = OperationalSpec(
        goal=_GOAL,
        criteria=[
            Criterion(id="step_k1", text="kinase domain", search_name="GenesByTaxon")
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="step_k1"),
        ),
    )
    _wire(monkeypatch)

    await eda_step.create_eda_step(ctx, attach_to_step_id="step_c1", slot="secondary")

    domain = ctx.deps.state.domain
    assert domain.answered_spec == domain.operational_spec
    assert domain.answered_graph == _graph(ctx).to_strategy_ast()


async def test_an_export_beside_the_strategy_is_stated_the_way_a_build_states_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A detached root is named by no criterion and by no structure node."""
    install_stub_api(monkeypatch)
    ctx = _lead_ctx_over(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
    ctx.deps.state.domain.operational_spec = _reference(_graph(ctx))
    _wire(monkeypatch)

    await eda_step.create_eda_step(ctx)

    graph = _graph(ctx)
    assert len(graph.roots) == 2
    assert ctx.deps.state.domain.operational_spec == _reference(graph)


async def test_a_structure_the_graph_does_not_hold_yet_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A framed structure states a plan, so an export does not overwrite it."""
    install_stub_api(monkeypatch)
    ctx = _lead_ctx_over(leaf("step_k1"))
    planned = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.UNION,
            inputs=[
                StructureNode(kind="leaf", criterion_id="step_k1"),
                StructureNode(kind="leaf", criterion_id="c_unbuilt"),
            ],
        ),
    )
    ctx.deps.state.domain.operational_spec = OperationalSpec(
        goal=_GOAL,
        criteria=[
            Criterion(id="step_k1", text="kinase domain", search_name="GenesByTaxon"),
            Criterion(id="c_unbuilt", text="secreted", search_name="GenesByTaxon"),
        ],
        structure=planned,
    )
    _wire(monkeypatch)

    await eda_step.create_eda_step(ctx)

    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert spec.structure == planned


class TestCombiningTheExportWithTheRoot:
    """The gesture WDK calls "add step": combine the export with the result."""

    def _ctx(self) -> RunContext[LeadDeps]:
        ctx = _lead_ctx_over(leaf("step_k1"))
        ctx.deps.state.domain.operational_spec = _reference(_graph(ctx))
        return ctx

    async def test_the_export_becomes_the_second_input_of_a_new_root(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_stub_api(monkeypatch)
        ctx = self._ctx()
        _wire(monkeypatch)

        answer = await eda_step.create_eda_step(
            ctx, combine_with_root=CombineOp.INTERSECT
        )

        exported = returned(answer, eda_step.EdaStepCreated).step_id
        graph = _graph(ctx)
        root_id = graph.primary_root_id()
        assert root_id is not None
        root = graph.steps[root_id]
        assert root.operator is CombineOp.INTERSECT
        assert root.primary_input_id == "step_k1"
        assert root.secondary_input_id == exported
        assert sorted(graph.steps) == sorted([root_id, "step_k1", exported])

    async def test_the_structure_names_the_new_combine_over_both(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_stub_api(monkeypatch)
        ctx = self._ctx()
        _wire(monkeypatch)

        answer = await eda_step.create_eda_step(
            ctx, combine_with_root=CombineOp.INTERSECT
        )

        exported = returned(answer, eda_step.EdaStepCreated).step_id
        spec = ctx.deps.state.domain.operational_spec
        assert spec is not None
        assert spec.structure == _reference(_graph(ctx)).structure
        assert structure_criteria(spec.structure) == {"step_k1", exported}

    async def test_the_result_and_the_summary_name_the_join(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_stub_api(monkeypatch)
        ctx = self._ctx()
        _wire(monkeypatch)

        answer = await eda_step.create_eda_step(
            ctx, combine_with_root=CombineOp.INTERSECT
        )

        result = returned(answer, eda_step.EdaStepCreated)
        assert result.combined_with_root is CombineOp.INTERSECT
        assert result.combine_step_id == _graph(ctx).primary_root_id()
        assert summary_of(answer).data["summary"] == (
            f"Step {result.step_id} combined with step_k1 (INTERSECT)"
        )

    async def test_a_join_beside_an_attach_point_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _wire(monkeypatch)

        with pytest.raises(ModelRetry) as raised:
            await eda_step.create_eda_step(
                self._ctx(),
                combine_with_root=CombineOp.INTERSECT,
                attach_to_step_id="step_k1",
            )

        assert "combine_with_root" in str(raised.value)
        assert "attach_to_step_id" in str(raised.value)

    async def test_a_join_beside_a_slot_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _wire(monkeypatch)

        with pytest.raises(ModelRetry) as raised:
            await eda_step.create_eda_step(
                self._ctx(), combine_with_root=CombineOp.UNION, slot="secondary"
            )

        assert "combine_with_root" in str(raised.value)
        assert "slot" in str(raised.value)

    async def test_a_join_beside_a_replace_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _wire(monkeypatch)

        with pytest.raises(ModelRetry) as raised:
            await eda_step.create_eda_step(
                self._ctx(),
                combine_with_root=CombineOp.INTERSECT,
                replace_step_id="step_k1",
            )

        assert "combine_with_root" in str(raised.value)
        assert "replace_step_id" in str(raised.value)

    async def test_a_strategy_with_two_roots_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _lead_ctx_over(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
        graph = _graph(ctx)
        graph.steps.update(flatten_tree(leaf("step_loose")))
        graph.recompute_roots()
        _wire(monkeypatch)

        with pytest.raises(ModelRetry) as raised:
            await eda_step.create_eda_step(ctx, combine_with_root=CombineOp.INTERSECT)

        message = str(raised.value)
        assert "step_c1" in message
        assert "step_loose" in message


async def test_an_export_clears_the_drop_it_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The criterion the drop states is realized once the export lands."""
    install_stub_api(monkeypatch)
    ctx = _lead_ctx_over(leaf("step_k1"))
    ctx.deps.state.domain.operational_spec = OperationalSpec(
        goal=_GOAL,
        criteria=[
            Criterion(id="step_k1", text="kinase domain", search_name="GenesByTaxon")
        ],
        dropped=[
            DroppedCriterion(
                text="essential in blood stages",
                reason="EDA-backed criterion",
                eda_dataset_id=PHENOTYPE_DATASET,
            ),
        ],
    )
    _wire(monkeypatch)

    await eda_step.create_eda_step(ctx, combine_with_root=CombineOp.INTERSECT)

    assert eda_backed_drops(ctx.deps.state.domain.operational_spec) == []


async def test_a_drop_on_another_dataset_stays(monkeypatch: pytest.MonkeyPatch) -> None:
    install_stub_api(monkeypatch)
    ctx = _lead_ctx_over(leaf("step_k1"))
    other = DroppedCriterion(
        text="febrile samples", reason="EDA-backed criterion", eda_dataset_id="DS_other"
    )
    ctx.deps.state.domain.operational_spec = OperationalSpec(
        goal=_GOAL, criteria=[], dropped=[other]
    )
    _wire(monkeypatch)

    await eda_step.create_eda_step(ctx, combine_with_root=CombineOp.INTERSECT)

    assert eda_backed_drops(ctx.deps.state.domain.operational_spec) == [other]


async def test_a_plan_that_rewires_built_steps_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A structure that joins built steps another way states a change to make."""
    install_stub_api(monkeypatch)
    ctx = _lead_ctx_over(
        StrategyStepNode(
            id="step_top",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(
                id="step_c1",
                search_name=COMBINE_SEARCH_NAME,
                operator=CombineOp.INTERSECT,
                primary_input=leaf("step_k1"),
                secondary_input=leaf("step_k2"),
            ),
        ),
    )
    planned = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.UNION,
            inputs=[
                StructureNode(kind="leaf", criterion_id="step_k1"),
                StructureNode(kind="leaf", criterion_id="step_k2"),
            ],
        ),
    )
    ctx.deps.state.domain.operational_spec = OperationalSpec(
        goal=_GOAL,
        criteria=[
            Criterion(id="step_k1", text="kinase domain", search_name="GenesByTaxon"),
            Criterion(id="step_k2", text="blood stages", search_name="GenesByTaxon"),
        ],
        structure=planned,
    )
    _wire(monkeypatch)

    await eda_step.create_eda_step(ctx, attach_to_step_id="step_top", slot="secondary")

    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert spec.structure == planned


async def test_a_bare_export_beside_the_strategy_keeps_the_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A step the strategy does not reach answers no criterion."""
    install_stub_api(monkeypatch)
    ctx = _lead_ctx_over(leaf("step_k1"))
    outstanding = DroppedCriterion(
        text="essential in blood stages",
        reason="EDA-backed criterion",
        eda_dataset_id=PHENOTYPE_DATASET,
    )
    ctx.deps.state.domain.operational_spec = OperationalSpec(
        goal=_GOAL,
        criteria=[
            Criterion(id="step_k1", text="kinase domain", search_name="GenesByTaxon")
        ],
        dropped=[outstanding],
    )
    _wire(monkeypatch)

    await eda_step.create_eda_step(ctx)

    assert len(_graph(ctx).roots) == 2
    assert eda_backed_drops(ctx.deps.state.domain.operational_spec) == [outstanding]
