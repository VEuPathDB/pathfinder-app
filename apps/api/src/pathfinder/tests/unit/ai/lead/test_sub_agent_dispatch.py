"""``build_strategy``: what it refuses, and what it leaves on the spec."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import sub_agent_dispatch
from pathfinder.ai.lead.sub_agent_dispatch import build_strategy
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.parameters.values import MultiPickValue
from pathfinder.domain.strategy.ast import COMBINE_SEARCH_NAME, StrategyStepNode
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.graph_model import flatten_tree
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.ops import CombineOp
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    lead_run_context,
    pipeline_state,
)


def _spec() -> OperationalSpec:
    return OperationalSpec(
        goal="proteases",
        criteria=[
            Criterion(
                id="step_text",
                text="protease text",
                search_name="GenesByText",
                role="seed",
                resolved_params={"organism": MultiPickValue(values=["Plasmodium"])},
            ),
            Criterion(id="step_go", text="proteolysis GO", search_name="GenesByGoTerm"),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="step_text"),
                    StructureNode(kind="leaf", criterion_id="step_go"),
                ],
            )
        ),
    )


def _combined_session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Test", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_join",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(id="step_text", search_name="GenesByText"),
            secondary_input=StrategyStepNode(id="step_go", search_name="GenesByGoTerm"),
        ),
    )
    graph.recompute_roots()
    session.graph = graph
    return session


def _ctx(
    *, with_strategy: bool, prompt: str = "use P. vivax for the GO criterion"
) -> RunContext[LeadDeps]:
    state = pipeline_state(
        user_prompt=prompt,
        domain=StrategyDomainState(operational_spec=_spec()),
    )
    session = (
        _combined_session() if with_strategy else StrategySession(site_id="plasmodb")
    )
    return lead_run_context(lead_deps(state, strategy_session=session))


async def test_build_strategy_dispatch_refuses_a_non_empty_strategy() -> None:
    with pytest.raises(ModelRetry) as excinfo:
        await build_strategy(_ctx(with_strategy=True))

    message = str(excinfo.value)
    assert "edit_strategy" in message
    assert "clear_strategy" in message
    # A camelCase name in a retry sends the model round a loop it cannot exit.
    assert "editStrategy" not in message


async def test_build_strategy_still_materializes_an_empty_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    produced: list[str] = []

    async def _fake_build(**kwargs: Any) -> BuildOutcome:
        produced.append(kwargs["root"].id)
        return BuildOutcome(pushed_step_ids=[kwargs["root"].id])

    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _fake_build)

    result = await build_strategy(_ctx(with_strategy=False))

    assert result.outcome.pushed_step_ids == produced


async def test_the_built_spec_is_re_keyed_on_the_step_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FRAME names a criterion with a label; the spec adopts the minted id."""
    produced: dict[str, str] = {}

    async def _fake_build(**kwargs: Any) -> BuildOutcome:
        root = kwargs["root"]
        produced["root"] = root.id
        produced["primary"] = root.primary_input.id
        produced["secondary"] = root.secondary_input.id
        return BuildOutcome(pushed_step_ids=[root.id])

    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _fake_build)
    ctx = _ctx(with_strategy=False, prompt="build it")

    await build_strategy(ctx)

    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert {c.id for c in spec.criteria} == {produced["primary"], produced["secondary"]}
    assert spec.structure is not None
    assert [node.criterion_id for node in spec.structure.root.inputs] == [
        produced["primary"],
        produced["secondary"],
    ]
    seed = next(c for c in spec.criteria if c.search_name == "GenesByText")
    assert seed.resolved_params == {"organism": MultiPickValue(values=["Plasmodium"])}


def _unconvertible() -> OperationalSpec:
    # Two inputs and no operator: bound, structured, and not a tree.
    return OperationalSpec(
        goal="drug targets",
        criteria=[
            Criterion(id=n, text=n, role="filter", search_name=f"By{n}")
            for n in ("a", "b")
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                inputs=[
                    StructureNode(kind="leaf", criterion_id="a"),
                    StructureNode(kind="leaf", criterion_id="b"),
                ],
            )
        ),
    )


def _mock_ctx(spec: OperationalSpec) -> Any:
    ctx = MagicMock()
    ctx.deps.state.domain.operational_spec = spec
    ctx.deps.runtime.user_id = uuid4()
    # A build only runs where there is no strategy; an existing one is an edit.
    ctx.deps.runtime.strategy_session.get_graph.return_value = None
    return ctx


class TestTheTurnSurvives:
    async def test_it_raises_model_retry(self) -> None:
        spec = _unconvertible()
        assert spec.ready_to_build

        with pytest.raises(ModelRetry):
            await build_strategy(_mock_ctx(spec))

    async def test_the_message_names_the_problem(self) -> None:
        with pytest.raises(ModelRetry) as err:
            await build_strategy(_mock_ctx(_unconvertible()))

        assert "combine" in str(err.value)

    async def test_the_message_says_the_structure_is_at_fault(self) -> None:
        with pytest.raises(ModelRetry) as err:
            await build_strategy(_mock_ctx(_unconvertible()))

        assert "structure" in str(err.value).lower()
