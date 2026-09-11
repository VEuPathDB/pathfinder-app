"""Every batch that replaces a subtree holds the criteria the spec states."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy.ast import COMBINE_SEARCH_NAME, StrategyStepNode
from veupathdb.domain.strategy.ops import CombineOp

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.strategy import apply_operations
from pathfinder.ai.tools.toolsets.execution import build_toolset
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.operations import (
    AddCombineOp,
    AddLeafOp,
    GraphOperation,
    ReplaceSubtreeOp,
)
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.operations.types import AttachNewRoot
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.services.strategies.commit import (
    apply_and_commit,
    apply_operations_and_commit,
)

from ._strategy_edit_stubs import (
    StubAPI,
    combine,
    ctx,
    install_stub_api,
    leaf,
    session_with,
)

_CRITERIA = {
    "step_k1": "kinase domain, PlasmoDB",
    "step_k2": "protein kinase InterPro",
    "step_ms": "mass spectrometry evidence",
}
_WDK_STEP_IDS = {
    "step_k1": 101,
    "step_k2": 102,
    "step_ms": 105,
    "step_u1": 201,
    "step_c1": 301,
}


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


def _strategy() -> StrategyStepNode:
    """``(k1 UNION k2) INTERSECT ms``."""
    union = combine("step_u1", leaf("step_k1"), leaf("step_k2"), op=CombineOp.UNION)
    return combine("step_c1", union, leaf("step_ms"))


def _deps() -> AgentDeps:
    return AgentDeps(
        site_id="plasmodb",
        strategy_session=session_with(_strategy(), _WDK_STEP_IDS),
        conversation_id=uuid4(),
        agent_state=AgentToolState(
            operational_spec_draft=OperationalSpec(
                goal="kinases with mass spec evidence",
                criteria=[
                    Criterion(id=sid, text=text, search_name="GenesByTaxon")
                    for sid, text in _CRITERIA.items()
                ],
            )
        ),
    )


def _placeholder_replacement() -> ReplaceSubtreeOp:
    return ReplaceSubtreeOp(
        step_id="step_u1",
        subtree=StrategyStepNode(id="step_p1", search_name="GenesByTaxon"),
    )


class TestTheApplyOperationsTool:
    async def test_a_batch_that_drops_criteria_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        deps = _deps()
        graph = deps.strategy_session.graph
        assert graph is not None
        revision = strategy_revision(graph.to_strategy_ast())

        with pytest.raises(ModelRetry) as excinfo:
            await apply_operations(ctx(deps), revision, [_placeholder_replacement()])

        assert "step_k1" in str(excinfo.value)
        assert "step_k2" in str(excinfo.value)
        assert set(graph.steps) == {
            "step_k1",
            "step_k2",
            "step_ms",
            "step_u1",
            "step_c1",
        }
        assert graph.steps["step_u1"].operator == CombineOp.UNION
        assert stub_api.calls == []

    async def test_a_batch_that_keeps_every_criterion_is_applied(
        self, stub_api: StubAPI
    ) -> None:
        deps = _deps()
        graph = deps.strategy_session.graph
        assert graph is not None
        revision = strategy_revision(graph.to_strategy_ast())
        kept = combine(
            "step_u1", leaf("step_k1"), leaf("step_k2"), op=CombineOp.INTERSECT
        )

        payload = (
            await apply_operations(
                ctx(deps),
                revision,
                [ReplaceSubtreeOp(step_id="step_u1", subtree=kept)],
            )
        ).return_value

        assert payload["applied"] == 1
        assert graph.steps["step_u1"].operator == CombineOp.INTERSECT
        assert stub_api.named("create_combined_step") != []

    @pytest.mark.usefixtures("stub_api")
    async def test_a_placeholder_inside_an_operation_never_validates(self) -> None:
        deps = _deps()
        toolset = build_toolset()
        tool = (await toolset.get_tools(ctx(deps)))["apply_operations"]

        with pytest.raises(ValidationError) as excinfo:
            tool.args_validator.validate_python(
                {
                    "base_revision": "r1",
                    "operations": [
                        {
                            "kind": "replaceSubtree",
                            "stepId": "step_u1",
                            "subtree": {"searchName": "__input_step__"},
                        }
                    ],
                }
            )

        assert "__input_step__" in str(excinfo.value)

    @pytest.mark.usefixtures("stub_api")
    async def test_a_real_search_name_inside_an_operation_validates(self) -> None:
        deps = _deps()
        toolset = build_toolset()
        tool = (await toolset.get_tools(ctx(deps)))["apply_operations"]

        args = tool.args_validator.validate_python(
            {
                "base_revision": "r1",
                "operations": [
                    {
                        "kind": "addLeaf",
                        "step": {"searchName": "GenesByTaxon", "id": "step_new"},
                        "attach": {"mode": "new-root"},
                    }
                ],
            }
        )

        assert args["operations"][0].step.search_name == "GenesByTaxon"


class TestTheCommitService:
    async def test_a_batch_that_drops_criteria_restores_the_graph(
        self, stub_api: StubAPI
    ) -> None:
        deps = _deps()
        graph = deps.strategy_session.graph
        assert graph is not None

        with pytest.raises(ApplyError) as excinfo:
            await apply_operations_and_commit(
                deps=deps.to_strategy_context(), ops=[_placeholder_replacement()]
            )

        assert "step_k1" in str(excinfo.value)
        assert set(graph.steps) == {
            "step_k1",
            "step_k2",
            "step_ms",
            "step_u1",
            "step_c1",
        }
        assert graph.steps["step_u1"].operator == CombineOp.UNION
        assert stub_api.calls == []

    async def test_one_operation_takes_the_same_refusal(
        self, stub_api: StubAPI
    ) -> None:
        deps = _deps()
        graph = deps.strategy_session.graph
        assert graph is not None

        with pytest.raises(ApplyError) as excinfo:
            await apply_and_commit(
                deps=deps.to_strategy_context(), op=_placeholder_replacement()
            )

        assert "step_k2" in str(excinfo.value)
        assert len(graph.steps) == 5
        assert stub_api.calls == []

    async def test_a_batch_that_mints_the_step_a_criterion_states_is_applied(
        self, stub_api: StubAPI
    ) -> None:
        """A criterion answers to the step the same batch adds for it."""
        deps = _deps()
        deps.agent_state.operational_spec_draft.criteria.append(
            Criterion(
                id="step_k3", text="secreted proteins", search_name="GenesByTaxon"
            )
        )
        graph = deps.strategy_session.graph
        assert graph is not None
        ops: list[GraphOperation] = [
            ReplaceSubtreeOp(
                step_id="step_k1",
                subtree=StrategyStepNode(
                    id="step_k1", search_name="GenesByMolecularWeight"
                ),
            ),
            AddLeafOp(step=leaf("step_k3"), attach=AttachNewRoot()),
            AddCombineOp(
                step=StrategyStepNode(
                    id="step_c2",
                    search_name=COMBINE_SEARCH_NAME,
                    operator=CombineOp.INTERSECT,
                ),
                left_id="step_c1",
                right_id="step_k3",
            ),
        ]

        result = await apply_operations_and_commit(
            deps=deps.to_strategy_context(), ops=ops
        )

        assert result.description != ""
        assert set(graph.steps) == {
            "step_k1",
            "step_k2",
            "step_ms",
            "step_u1",
            "step_c1",
            "step_k3",
            "step_c2",
        }
        assert graph.steps["step_k1"].search_name == "GenesByMolecularWeight"
        assert graph.steps["step_c2"].secondary_input_id == "step_k3"
        assert stub_api.named("create_combined_step") != []

    async def test_a_batch_the_spec_does_not_address_is_left_alone(
        self, stub_api: StubAPI
    ) -> None:
        """A spec whose ids name no live step states nothing about this graph."""
        deps = _deps()
        deps.agent_state.operational_spec_draft.criteria = [
            Criterion(id="c1", text="a criterion of another graph")
        ]
        graph = deps.strategy_session.graph
        assert graph is not None

        result = await apply_operations_and_commit(
            deps=deps.to_strategy_context(), ops=[_placeholder_replacement()]
        )

        assert result.description != ""
        assert graph.steps["step_p1"].search_name == "GenesByTaxon"
        assert stub_api.named("create_step") != []
