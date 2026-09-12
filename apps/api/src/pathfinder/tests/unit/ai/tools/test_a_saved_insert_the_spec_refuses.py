"""A saved insert the spec refuses answers the agent, not an unhandled error."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone import strategy_edits
from pathfinder.ai.tools.standalone.strategy_edits import insert_saved_strategy
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.tests._support.database import detached_session

from ._strategy_edit_stubs import ctx, leaf, session_with

_TARGET = "step_780fd940"
_REFUSAL = "the criterion 'binding' states go_term = 'GO:0005515'"


def _deps() -> AgentDeps:
    return AgentDeps(
        site_id="plasmodb",
        strategy_session=session_with(leaf(_TARGET), {_TARGET: 440_432_473}),
        conversation_id=uuid4(),
        db_session_factory=detached_session,
    )


async def test_the_refusal_reaches_the_agent_as_a_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _refuse(**_kwargs: Any) -> None:
        raise ApplyError(_REFUSAL)

    monkeypatch.setattr(strategy_edits, "insert_saved_into_conversation", _refuse)
    deps = _deps()

    with pytest.raises(ModelRetry) as excinfo:
        await insert_saved_strategy(
            ctx(deps), _TARGET, 7777, operator=CombineOp.INTERSECT
        )

    message = str(excinfo.value)
    assert message.startswith("REJECTED: ")
    assert _REFUSAL in message
    assert "Nothing was inserted and the strategy is unchanged." in message
