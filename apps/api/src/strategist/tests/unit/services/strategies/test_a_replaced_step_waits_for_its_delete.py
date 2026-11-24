from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from strategist.persistence.models import (
    ConversationStrategyView,
    PersistedStrategyGraph,
)
from strategist.persistence.repositories.conversation_update import (
    ConversationUpdate,
)
from strategist.services.strategies.session_factory import build_strategy_session
from strategist.services.strategies.sync_state import ensure_sync_state

_AST = StrategyAst(
    record_type="transcript",
    root=StrategyStepNode(id="step_a", search_name="GenesByTaxon"),
    wdk_step_ids={"step_a": 440537303},
)


def test_a_rebuilt_session_still_holds_the_ids_waiting_for_their_delete() -> None:
    session = build_strategy_session(
        site_id="plasmodb",
        strategy_graph=PersistedStrategyGraph(
            id=str(uuid4()),
            name="Kinases",
            strategy_ast=_AST,
            wdk_strategy_id=330679883,
            replaced_wdk_step_ids=[440537293],
        ),
    )

    assert ensure_sync_state(session).replaced_wdk_step_ids == [440537293]


def test_the_ids_waiting_for_their_delete_are_written_with_the_strategy() -> None:
    values = ConversationUpdate(replaced_wdk_step_ids=[440537293]).strategy_values()

    assert values["replaced_wdk_step_ids"] == [440537293]
    assert ConversationStrategyView().replaced_wdk_step_ids == []
