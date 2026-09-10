"""A saved strategy is the one criterion that references it, however it is wrapped."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SavedStrategyRef,
    SpecStructure,
    StructureNode,
    build_step_tree,
    renumber_criteria,
)
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.tree import walk

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.strategy_edits import replace_subtree

from ._strategy_edit_stubs import StubAPI, combine, ctx, install_stub_api, session_with


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


def _saved_strategy_spec() -> OperationalSpec:
    """An InterPro leaf intersected with a saved strategy of two searches."""
    saved = combine(
        "saved_root",
        StrategyStepNode(id="saved_a", search_name="GenesByGoTerm"),
        StrategyStepNode(id="saved_b", search_name="GenesByText"),
        op=CombineOp.UNION,
    )
    return OperationalSpec(
        goal="kinases",
        criteria=[
            Criterion(
                id="c1", text="InterPro kinase domain", search_name="GenesByInterpro"
            ),
            Criterion(
                id="c2",
                text="the saved kinase strategy",
                saved_strategy_ref=SavedStrategyRef(
                    conversation_id="conv",
                    name="kinases",
                    wdk_strategy_id=999,
                    step_count=3,
                    subtree=saved,
                ),
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="c1"),
                    StructureNode(kind="leaf", criterion_id="c2"),
                ],
            )
        ),
    )


def _saved_strategy_deps() -> AgentDeps:
    spec = _saved_strategy_spec()
    built = build_step_tree(spec)
    renumbered = renumber_criteria(spec, built.step_id_by_criterion)
    wdk_ids = {node.id: 700 + i for i, node in enumerate(walk(built.root))}
    return AgentDeps(
        site_id="plasmodb",
        strategy_session=session_with(built.root, wdk_ids),
        conversation_id=uuid4(),
        agent_state=AgentToolState(operational_spec_draft=renumbered),
    )


class TestASavedStrategyReference:
    async def test_a_valid_replacement_over_an_expansion_is_applied(
        self, stub_api: StubAPI
    ) -> None:
        deps = _saved_strategy_deps()
        graph = deps.strategy_session.graph
        assert graph is not None
        interpro = next(
            sid
            for sid, step in graph.steps.items()
            if step.search_name == "GenesByInterpro"
        )

        payload = (
            await replace_subtree(
                ctx(deps),
                interpro,
                StrategyStepNode(id=interpro, search_name="GenesByInterpro"),
            )
        ).return_value

        assert payload["ok"] is True
        assert len(graph.steps) == 5
        assert stub_api.named("update_step_search_config") != []

    async def test_a_replacement_that_drops_the_expansion_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        deps = _saved_strategy_deps()
        graph = deps.strategy_session.graph
        assert graph is not None
        root_id = graph.primary_root_id()
        assert root_id is not None
        saved_root = graph.steps[root_id].secondary_input_id
        assert saved_root is not None

        with pytest.raises(ModelRetry) as excinfo:
            await replace_subtree(
                ctx(deps),
                root_id,
                StrategyStepNode(id="step_only", search_name="GenesByInterpro"),
            )

        assert saved_root in str(excinfo.value)
        assert "the saved kinase strategy" in str(excinfo.value)
        assert len(graph.steps) == 5
        assert stub_api.calls == []


def _only_saved_strategy_spec() -> OperationalSpec:
    """One criterion, a saved strategy of two searches, with no combine over it."""
    saved = combine(
        "saved_root",
        StrategyStepNode(id="saved_a", search_name="GenesByGoTerm"),
        StrategyStepNode(id="saved_b", search_name="GenesByText"),
        op=CombineOp.UNION,
    )
    return OperationalSpec(
        goal="the saved kinases",
        criteria=[
            Criterion(
                id="c1",
                text="the saved kinase strategy",
                saved_strategy_ref=SavedStrategyRef(
                    conversation_id="conv",
                    name="kinases",
                    wdk_strategy_id=999,
                    step_count=3,
                    subtree=saved,
                ),
            ),
        ],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="c1")),
    )


def _only_saved_strategy_deps() -> AgentDeps:
    spec = _only_saved_strategy_spec()
    built = build_step_tree(spec)
    renumbered = renumber_criteria(spec, built.step_id_by_criterion)
    wdk_ids = {node.id: 800 + i for i, node in enumerate(walk(built.root))}
    return AgentDeps(
        site_id="plasmodb",
        strategy_session=session_with(built.root, wdk_ids),
        conversation_id=uuid4(),
        agent_state=AgentToolState(operational_spec_draft=renumbered),
    )


class TestASavedStrategyWithNoCombineOverIt:
    async def test_a_valid_replacement_inside_the_expansion_is_applied(
        self, stub_api: StubAPI
    ) -> None:
        deps = _only_saved_strategy_deps()
        graph = deps.strategy_session.graph
        assert graph is not None
        assert len(graph.steps) == 3
        go_term = next(
            sid
            for sid, step in graph.steps.items()
            if step.search_name == "GenesByGoTerm"
        )

        payload = (
            await replace_subtree(
                ctx(deps),
                go_term,
                StrategyStepNode(
                    id=go_term,
                    search_name="GenesByGoTerm",
                    display_name="protein kinase activity",
                ),
            )
        ).return_value

        assert payload["ok"] is True
        assert len(graph.steps) == 3
        assert graph.steps[go_term].display_name == "protein kinase activity"
        assert stub_api.named("update_step_search_config") != []

    async def test_a_replacement_that_drops_the_expansion_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        deps = _only_saved_strategy_deps()
        graph = deps.strategy_session.graph
        assert graph is not None
        root_id = graph.primary_root_id()
        assert root_id is not None

        with pytest.raises(ModelRetry) as excinfo:
            await replace_subtree(
                ctx(deps),
                root_id,
                StrategyStepNode(id="step_only", search_name="GenesByInterpro"),
            )

        message = str(excinfo.value)
        assert root_id in message
        assert "the saved kinase strategy" in message
        assert len(graph.steps) == 3
        assert stub_api.calls == []
