from __future__ import annotations

from typing import NoReturn

import pytest
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from strategist.persistence.models import PersistedStrategyGraph
from strategist.platform.errors import ErrorCode, StrategyAstCorruptError
from strategist.services.strategies import session_factory
from strategist.services.strategies.session_factory import build_strategy_session

_THREAD = "6f1c2e0a-0000-4000-8000-000000000001"


def _does_not_load(root: StrategyStepNode) -> NoReturn:
    msg = f"step {root.id} names an input the tree does not hold"
    raise KeyError(msg)


def test_a_plan_whose_tree_does_not_load_refuses_the_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_factory, "flatten_tree", _does_not_load)
    stored = StrategyAst.model_validate(
        {
            "recordType": "transcript",
            "root": {"id": "step_a", "searchName": "GenesByText"},
        }
    )

    with pytest.raises(StrategyAstCorruptError) as refused:
        build_strategy_session(
            site_id="plasmodb",
            strategy_graph=PersistedStrategyGraph(
                id=_THREAD, name="kinases", strategy_ast=stored
            ),
        )

    assert (refused.value.code, refused.value.detail) == (
        ErrorCode.STRATEGY_AST_CORRUPT,
        (
            f"conversation {_THREAD} holds a strategy_ast that does not parse: "
            "'step step_a names an input the tree does not hold'"
        ),
    )
