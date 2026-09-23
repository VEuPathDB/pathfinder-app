"""A loaded session knows whether WDK already holds its tree."""

from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyAst,
    StrategyStepNode,
)
from veupathdb.wdk import build_wdk_step_tree

from pathfinder.persistence.models import PersistedStrategyGraph
from pathfinder.services.strategies.session_factory import build_strategy_session
from pathfinder.services.strategies.sync_state import ensure_sync_state

_IDS = {"step_a": 101, "step_b": 102, "step_join": 103}
_ORGANISM = MultiPickValue(values=["Plasmodium falciparum 3D7"])


def _root() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_join",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id="step_a", search_name="GenesByTaxon", parameters={"organism": _ORGANISM}
        ),
        secondary_input=StrategyStepNode(
            id="step_b",
            search_name="GenesWithSignalPeptide",
            parameters={"organism": _ORGANISM},
        ),
    )


def _persisted(errors: dict[str, str] | None) -> PersistedStrategyGraph:
    return PersistedStrategyGraph(
        id=str(uuid4()),
        name="restored",
        strategy_ast=StrategyAst(
            record_type="transcript",
            root=_root(),
            wdk_step_ids=dict(_IDS),
            wdk_push_errors=errors,
        ),
        wdk_strategy_id=555,
    )


def test_a_stored_strategy_with_no_push_error_restores_the_tree_wdk_holds() -> None:
    session = build_strategy_session(
        site_id="plasmodb", strategy_graph=_persisted(None)
    )
    state = ensure_sync_state(session)

    assert state.wdk_step_tree == build_wdk_step_tree(_root(), _IDS)
    assert state.wdk_push_errors == {}


def test_a_stored_push_error_survives_the_load_and_leaves_the_tree_unrecorded() -> None:
    session = build_strategy_session(
        site_id="plasmodb", strategy_graph=_persisted({"step_b": "HTTP 422 from WDK"})
    )
    state = ensure_sync_state(session)

    assert state.wdk_step_tree is None
    assert state.wdk_push_errors == {"step_b": "HTTP 422 from WDK"}


def _named(conversation_name: str, ast_name: str | None) -> str:
    persisted = _persisted(None)
    assert persisted.strategy_ast is not None
    persisted = persisted.model_copy(
        update={
            "name": conversation_name,
            "strategy_ast": persisted.strategy_ast.model_copy(
                update={"name": ast_name}
            ),
        }
    )
    session = build_strategy_session(site_id="plasmodb", strategy_graph=persisted)
    assert session.graph is not None
    return session.graph.name


def test_the_graph_carries_the_threads_name_over_the_stored_one() -> None:
    assert _named("Kinase hunt", "New Conversation") == "Kinase hunt"


def test_an_unnamed_thread_keeps_the_stored_name() -> None:
    assert _named("", "Kinase hunt") == "Kinase hunt"


def test_a_thread_and_a_strategy_with_no_name_take_the_default() -> None:
    assert _named("", None) == "New Conversation"
