"""A write into an input slot never takes the step that slot holds off the tree."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import JsonValue
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import COMBINE_SEARCH_NAME, CombineOp, StrategyStepNode

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_step
from pathfinder.ai.tools.standalone.strategy import apply_operations
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.operations import (
    AddCombineOp,
    AddLeafOp,
    EditableOperation,
    WireInputOp,
)
from pathfinder.domain.strategy.operations.types import AttachIntoSlot, AttachNewRoot
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.stated_shape import stated_shape
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._eda_step_doubles import (
    bound,
    read_detail,
    wire_gene_count,
)

from ._strategy_edit_stubs import (
    StubAPI,
    combine,
    ctx,
    install_stub_api,
    leaf,
    session_with,
)

_EDA_WDK_IDS = {"step_k1": 101, "step_k2": 102, "step_c1": 301}
_BATCH_WDK_IDS = {"step_k1": 101, "step_k2": 102, "step_ms": 105}


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


def _eda_spec() -> OperationalSpec:
    return OperationalSpec(
        goal="febrile kinases",
        criteria=[
            Criterion(id="step_k1", text="kinase domain", search_name="GenesByTaxon"),
            Criterion(id="step_k2", text="kinase GO term", search_name="GenesByTaxon"),
        ],
    )


def _eda_ctx(
    monkeypatch: pytest.MonkeyPatch,
    root: StrategyStepNode,
    spec: OperationalSpec | None,
) -> RunContext[LeadDeps]:
    monkeypatch.setattr(eda_step, "bound_analysis", bound)
    monkeypatch.setattr(eda_step, "read_analysis", read_detail)
    wire_gene_count(monkeypatch)
    run_ctx = lead_run_context(
        user_prompt="export the febrile subset",
        strategy_session=session_with(root, _EDA_WDK_IDS),
    )
    run_ctx.deps.state.domain.operational_spec = spec
    return run_ctx


class TestAnEdaExportIntoASlot:
    async def test_an_export_into_an_occupied_slot_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, stub_api: StubAPI
    ) -> None:
        run_ctx = _eda_ctx(
            monkeypatch,
            combine("step_c1", leaf("step_k1"), leaf("step_k2")),
            _eda_spec(),
        )
        graph = run_ctx.deps.runtime.strategy_session.graph
        assert graph is not None

        with pytest.raises(ModelRetry) as excinfo:
            await eda_step.create_eda_step(
                run_ctx, attach_to_step_id="step_c1", slot="secondary"
            )

        message = str(excinfo.value)
        assert "secondary" in message
        assert "step_c1" in message
        assert "step_k2" in message
        assert "kinase GO term" in message
        assert set(graph.steps) == {"step_c1", "step_k1", "step_k2"}
        assert graph.steps["step_c1"].secondary_input_id == "step_k2"
        assert stub_api.calls == []
        spec = run_ctx.deps.state.domain.operational_spec
        assert spec is not None
        assert [c.id for c in spec.criteria] == ["step_k1", "step_k2"]
        shape = stated_shape(
            graph=graph,
            root_id="step_c1",
            criteria={"step_k1", "step_k2"},
            outside=set(),
        )
        assert shape.holds is True

    async def test_an_export_into_a_free_slot_applies_and_states_its_criterion(
        self, monkeypatch: pytest.MonkeyPatch, stub_api: StubAPI
    ) -> None:
        one_input = StrategyStepNode(
            id="step_c1",
            search_name=COMBINE_SEARCH_NAME,
            primary_input=leaf("step_k1"),
            operator=CombineOp.INTERSECT,
        )
        spec = OperationalSpec(
            goal="febrile kinases",
            criteria=[
                Criterion(
                    id="step_k1", text="kinase domain", search_name="GenesByTaxon"
                )
            ],
        )
        run_ctx = _eda_ctx(monkeypatch, one_input, spec)
        graph = run_ctx.deps.runtime.strategy_session.graph
        assert graph is not None

        answer = await eda_step.create_eda_step(
            run_ctx, attach_to_step_id="step_c1", slot="secondary"
        )

        result = returned(answer, eda_step.EdaStepCreated)
        exported = result.step_id
        assert graph.steps["step_c1"].secondary_input_id == exported
        assert graph.steps[exported].search_name == "GenesByEdaSubset"
        assert stub_api.named("create_step") != []
        stated = run_ctx.deps.state.domain.operational_spec
        assert stated is not None
        assert [c.id for c in stated.criteria] == ["step_k1", exported]
        assert stated.criteria[1].text == "berghei subset"


def _batch_strategy() -> StrategyStepNode:
    """``(k1 UNION k2) INTERSECT ms``."""
    union = combine("step_u1", leaf("step_k1"), leaf("step_k2"), op=CombineOp.UNION)
    return combine("step_c1", union, leaf("step_ms"))


def _batch_deps() -> AgentDeps:
    return AgentDeps(
        site_id="plasmodb",
        strategy_session=session_with(
            _batch_strategy(), {**_BATCH_WDK_IDS, "step_u1": 201, "step_c1": 301}
        ),
        conversation_id=uuid4(),
    )


def _revision(deps: AgentDeps) -> str:
    graph = deps.strategy_session.graph
    assert graph is not None
    return strategy_revision(graph.to_strategy_ast())


class TestABatchThatWritesASlot:
    async def test_a_new_leaf_wired_into_an_occupied_slot_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        deps = _batch_deps()
        graph = deps.strategy_session.graph
        assert graph is not None
        op: EditableOperation = AddLeafOp(
            step=leaf("step_new"),
            attach=AttachIntoSlot(target_step_id="step_c1", slot="secondary"),
        )

        with pytest.raises(ModelRetry) as excinfo:
            await apply_operations(ctx(deps), _revision(deps), [op])

        message = str(excinfo.value)
        assert "step_ms" in message
        assert "secondary" in message
        assert set(graph.steps) == {
            "step_c1",
            "step_u1",
            "step_k1",
            "step_k2",
            "step_ms",
        }
        assert graph.steps["step_c1"].secondary_input_id == "step_ms"
        assert stub_api.calls == []

    async def test_a_wire_that_takes_a_branch_off_the_tree_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        deps = _batch_deps()
        graph = deps.strategy_session.graph
        assert graph is not None
        op: EditableOperation = WireInputOp(
            target_step_id="step_c1", slot="primary", source_step_id="step_k1"
        )

        with pytest.raises(ModelRetry) as excinfo:
            await apply_operations(ctx(deps), _revision(deps), [op])

        assert "step_u1" in str(excinfo.value)
        assert graph.steps["step_c1"].primary_input_id == "step_u1"
        assert stub_api.calls == []

    async def test_a_wire_into_a_combine_over_the_step_it_replaces_applies(
        self, stub_api: StubAPI
    ) -> None:
        deps = _batch_deps()
        graph = deps.strategy_session.graph
        assert graph is not None
        ops: list[EditableOperation] = [
            AddLeafOp(step=leaf("step_new"), attach=AttachNewRoot()),
            AddCombineOp(
                step=StrategyStepNode(
                    id="step_c2",
                    search_name=COMBINE_SEARCH_NAME,
                    operator=CombineOp.INTERSECT,
                ),
                left_id="step_ms",
                right_id="step_new",
            ),
            WireInputOp(
                target_step_id="step_c1", slot="secondary", source_step_id="step_c2"
            ),
        ]

        payload = returned(
            await apply_operations(ctx(deps), _revision(deps), ops),
            dict[str, JsonValue],
        )

        assert payload["applied"] == 3
        assert graph.steps["step_c1"].secondary_input_id == "step_c2"
        assert graph.steps["step_c2"].primary_input_id == "step_ms"
        assert stub_api.named("create_combined_step") != []
