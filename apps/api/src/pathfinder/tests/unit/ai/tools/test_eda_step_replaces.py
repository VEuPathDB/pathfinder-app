"""``create_eda_step`` puts the export in the place of a step already held."""

from __future__ import annotations

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
    DroppedCriterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    eda_backed_drops,
    structure_criteria,
)
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.spec_hydration import spec_from_ast
from pathfinder.tests._support.eda_wire import PHENOTYPE_DATASET
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._eda_step_doubles import (
    bound,
    read_detail,
    recording_commit,
    wire_gene_count,
)
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    combine,
    install_stub_api,
    leaf,
    session_with,
)


def _wire(monkeypatch: pytest.MonkeyPatch, *, commit: object | None = None) -> None:
    monkeypatch.setattr(eda_step, "bound_analysis", bound)
    monkeypatch.setattr(eda_step, "read_analysis", read_detail)
    wire_gene_count(monkeypatch)
    if commit is not None:
        monkeypatch.setattr(eda_step, "apply_operations_and_commit", commit)


_BATCH_REFUSAL = "a replaced subtree would leave the strategy holding []"


def _lead_ctx_over(root: StrategyStepNode) -> RunContext[LeadDeps]:
    """A Lead context whose session already holds a strategy."""
    return lead_run_context(
        user_prompt="export the febrile subset", strategy_session=session_with(root, {})
    )


def _two_kinase_criteria() -> OperationalSpec:
    return OperationalSpec(
        goal="essential kinases",
        criteria=[
            Criterion(id="step_k1", text="kinase domain", search_name="GenesByTaxon"),
            Criterion(
                id="step_k2",
                text="essential in blood stages",
                search_name="GenesByTaxon",
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="step_k1"),
                    StructureNode(kind="leaf", criterion_id="step_k2"),
                ],
            ),
        ),
    )


class TestAnExportThatTakesAStepsPlace:
    async def test_replace_step_id_builds_a_replace_subtree_operation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _lead_ctx_over(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
        applied: list[Any] = []
        _wire(monkeypatch, commit=recording_commit(applied))

        await eda_step.create_eda_step(ctx, replace_step_id="step_k2")

        op = applied[0][0]
        assert op.kind == "replaceSubtree"
        assert op.step_id == "step_k2"
        assert op.subtree.search_name == "GenesByEdaSubset"

    async def test_the_result_names_the_step_it_replaced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _lead_ctx_over(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
        applied: list[Any] = []
        _wire(monkeypatch, commit=recording_commit(applied, dropped=["step_k2"]))

        answer = await eda_step.create_eda_step(ctx, replace_step_id="step_k2")

        result = returned(answer, eda_step.EdaStepCreated)
        assert result.replaced_step_id == "step_k2"
        assert result.dropped_step_ids == ["step_k2"]

    async def test_a_replace_beside_an_attach_point_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _lead_ctx_over(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
        _wire(monkeypatch)

        with pytest.raises(ModelRetry) as excinfo:
            await eda_step.create_eda_step(
                ctx,
                replace_step_id="step_k2",
                attach_to_step_id="step_c1",
                slot="secondary",
            )

        message = str(excinfo.value)
        assert "replace_step_id" in message
        assert "attach_to_step_id" in message

    async def test_a_step_the_strategy_does_not_hold_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _lead_ctx_over(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
        _wire(monkeypatch)

        with pytest.raises(ModelRetry) as excinfo:
            await eda_step.create_eda_step(ctx, replace_step_id="step_gone")

        message = str(excinfo.value)
        assert "step_gone" in message
        assert "'step_c1', 'step_k1', 'step_k2'" in message


class TestAReplacementThatReachesTheCommit:
    """The write passes the spec guard, so the export lands in the tree."""

    async def test_the_export_takes_the_place_of_the_step_it_replaces(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = install_stub_api(monkeypatch)
        ctx = _lead_ctx_over(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
        ctx.deps.state.domain.operational_spec = _two_kinase_criteria()
        _wire(monkeypatch)
        graph = ctx.deps.runtime.strategy_session.graph
        assert graph is not None

        answer = await eda_step.create_eda_step(ctx, replace_step_id="step_k2")

        result = returned(answer, eda_step.EdaStepCreated)
        exported = result.step_id
        assert graph.steps["step_c1"].secondary_input_id == exported
        assert "step_k2" not in graph.steps
        assert result.replaced_step_id == "step_k2"
        assert result.dropped_step_ids == ["step_k2"]
        assert api.named("create_step") != []

    async def test_the_spec_states_the_export_where_the_old_criterion_stood(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_stub_api(monkeypatch)
        ctx = _lead_ctx_over(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
        ctx.deps.state.domain.operational_spec = _two_kinase_criteria()
        _wire(monkeypatch)

        answer = await eda_step.create_eda_step(ctx, replace_step_id="step_k2")

        exported = returned(answer, eda_step.EdaStepCreated).step_id
        spec = ctx.deps.state.domain.operational_spec
        assert spec is not None
        assert [c.id for c in spec.criteria] == ["step_k1", exported]
        assert spec.criteria[1].text == "berghei subset"
        assert spec.criteria[1].search_name == "GenesByEdaSubset"


async def test_a_refused_replacement_leaves_the_spec_as_it_found_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The spec follows the strategy, so a write that lands nothing states nothing."""
    ctx = _lead_ctx_over(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
    spec = _two_kinase_criteria()
    ctx.deps.state.domain.operational_spec = spec

    async def refusing_commit(*, deps: object, ops: list[Any]) -> None:
        del deps, ops
        raise ValidationError(title="VEuPathDB refused the step", detail="no")

    _wire(monkeypatch, commit=refusing_commit)

    with pytest.raises(ModelRetry):
        await eda_step.create_eda_step(ctx, replace_step_id="step_k2")

    assert ctx.deps.state.domain.operational_spec is spec
    assert [c.id for c in spec.criteria] == ["step_k1", "step_k2"]


async def test_a_batch_the_graph_refuses_comes_back_as_a_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other write tools answer a refused batch with a retry, and so does this."""
    ctx = _lead_ctx_over(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
    spec = _two_kinase_criteria()
    ctx.deps.state.domain.operational_spec = spec

    async def refusing_commit(*, deps: object, ops: list[Any]) -> None:
        del deps, ops
        raise ApplyError(_BATCH_REFUSAL)

    _wire(monkeypatch, commit=refusing_commit)

    with pytest.raises(ModelRetry) as excinfo:
        await eda_step.create_eda_step(ctx, replace_step_id="step_k2")

    message = str(excinfo.value)
    assert message.startswith("One operation this export writes was refused")
    assert "a replaced subtree would leave" in message
    assert "Nothing was applied" in message
    assert ctx.deps.state.domain.operational_spec is spec
    assert [c.id for c in spec.criteria] == ["step_k1", "step_k2"]


class TestTheStructureAfterAReplacement:
    """The structure names the export where it named the step it replaced."""

    async def test_the_combine_keeps_its_operator_and_names_the_export(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_stub_api(monkeypatch)
        ctx = _lead_ctx_over(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
        ctx.deps.state.domain.operational_spec = _two_kinase_criteria()
        _wire(monkeypatch)

        answer = await eda_step.create_eda_step(ctx, replace_step_id="step_k2")

        exported = returned(answer, eda_step.EdaStepCreated).step_id
        spec = ctx.deps.state.domain.operational_spec
        assert spec is not None
        assert spec.structure is not None
        assert structure_criteria(spec.structure) == {"step_k1", exported}
        assert spec.structure.root.kind == "combine"
        assert spec.structure.root.operator is CombineOp.INTERSECT
        assert [c.id for c in spec.criteria] == ["step_k1", exported]

    async def test_replacing_the_root_leaves_the_export_as_the_only_leaf(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_stub_api(monkeypatch)
        ctx = _lead_ctx_over(leaf("step_k1"))
        ctx.deps.state.domain.operational_spec = OperationalSpec(
            goal="essential kinases",
            criteria=[
                Criterion(
                    id="step_k1", text="kinase domain", search_name="GenesByTaxon"
                )
            ],
            structure=SpecStructure(
                root=StructureNode(kind="leaf", criterion_id="step_k1"),
            ),
        )
        _wire(monkeypatch)

        answer = await eda_step.create_eda_step(ctx, replace_step_id="step_k1")

        exported = returned(answer, eda_step.EdaStepCreated).step_id
        spec = ctx.deps.state.domain.operational_spec
        assert spec is not None
        assert spec.structure is not None
        assert spec.structure.root.kind == "leaf"
        assert spec.structure.root.criterion_id == exported
        assert [c.id for c in spec.criteria] == [exported]


async def test_replacing_a_combine_names_the_export_where_it_stood(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A combine carries no criterion id, so the structure is restated."""
    install_stub_api(monkeypatch)
    ctx = _lead_ctx_over(
        combine(
            "step_top",
            combine("step_sub", leaf("step_k1"), leaf("step_k2"), op=CombineOp.UNION),
            leaf("step_k3"),
        ),
    )
    graph = ctx.deps.runtime.strategy_session.graph
    assert graph is not None
    ast = graph.to_strategy_ast()
    assert ast is not None
    ctx.deps.state.domain.operational_spec = spec_from_ast(ast, goal="kinases")
    _wire(monkeypatch)

    answer = await eda_step.create_eda_step(ctx, replace_step_id="step_sub")

    exported = returned(answer, eda_step.EdaStepCreated).step_id
    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert structure_criteria(spec.structure) == {"step_k3", exported}
    assert spec.structure is not None
    assert spec.structure.root.operator is CombineOp.INTERSECT
    assert [c.id for c in spec.criteria] == ["step_k3", exported]


async def test_a_replacement_clears_the_drop_it_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_stub_api(monkeypatch)
    ctx = _lead_ctx_over(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
    spec = _two_kinase_criteria()
    spec.dropped = [
        DroppedCriterion(
            text="essential in blood stages",
            reason="EDA-backed criterion",
            eda_dataset_id=PHENOTYPE_DATASET,
        ),
    ]
    ctx.deps.state.domain.operational_spec = spec
    _wire(monkeypatch)

    await eda_step.create_eda_step(ctx, replace_step_id="step_k2")

    assert eda_backed_drops(ctx.deps.state.domain.operational_spec) == []


async def test_replacing_a_step_the_spec_does_not_state_states_the_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The structure names the export, so a later edit does not drop it."""
    install_stub_api(monkeypatch)
    ctx = _lead_ctx_over(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
    ctx.deps.state.domain.operational_spec = OperationalSpec(
        goal="essential kinases",
        criteria=[
            Criterion(id="step_k1", text="kinase domain", search_name="GenesByTaxon")
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="step_k1"),
        ),
    )
    _wire(monkeypatch)

    answer = await eda_step.create_eda_step(ctx, replace_step_id="step_k2")

    exported = returned(answer, eda_step.EdaStepCreated).step_id
    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert [c.id for c in spec.criteria] == ["step_k1", exported]
    assert structure_criteria(spec.structure) == {"step_k1", exported}
