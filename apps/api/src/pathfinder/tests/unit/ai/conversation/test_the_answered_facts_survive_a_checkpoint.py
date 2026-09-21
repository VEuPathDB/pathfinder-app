"""The answered spec and the answered tree through the checkpoint serializer."""

from __future__ import annotations

from assistant_core.conversation.serde import build_checkpoint_serde

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.assistants.pathfinder_spec import PATHFINDER_CHECKPOINT_TYPES
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    built_spec,
    built_tree,
    session_holding,
)


def test_a_domain_holding_both_answered_facts_survives_the_strict_serializer() -> None:
    graph = session_holding(built_tree()).get_graph(None)
    assert graph is not None
    domain = StrategyDomainState(
        operational_spec=built_spec(),
        answered_spec=built_spec(),
        answered_graph=graph.to_strategy_ast(),
    )
    serde = build_checkpoint_serde(PATHFINDER_CHECKPOINT_TYPES)

    restored = serde.loads_typed(serde.dumps_typed(domain))

    assert isinstance(restored, StrategyDomainState)
    assert restored.answered_graph == domain.answered_graph
    assert restored.answered_spec == domain.answered_spec
