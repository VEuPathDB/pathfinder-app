"""An imported WDK strategy takes its own name, its root's name, then its id."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode

from pathfinder.services.strategies.wdk_sync import wdk_chat_name

_WDK_ID = 330679883
_BOOLEAN = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"


def _leaf(name: str | None, step_id: str = "440537303") -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id, search_name="GenesByExportPred", display_name=name
    )


def _ast(name: str | None, root: StrategyStepNode) -> StrategyAst:
    return StrategyAst(record_type="transcript", name=name, root=root)


@pytest.mark.parametrize(
    ("ast", "expected"),
    [
        (_ast("Exported kinases", _leaf("exported")), "Exported kinases"),
        (_ast(None, _leaf("exported")), "exported"),
        (_ast(None, _leaf("GenesByExportPred")), f"WDK Strategy {_WDK_ID}"),
        (
            _ast(
                None,
                StrategyStepNode(
                    id="440537323",
                    search_name=_BOOLEAN,
                    display_name=_BOOLEAN,
                    operator=CombineOp.INTERSECT,
                    primary_input=_leaf("exported"),
                    secondary_input=_leaf("secreted", "440537313"),
                ),
            ),
            f"WDK Strategy {_WDK_ID}",
        ),
    ],
)
def test_the_name_an_import_takes(ast: StrategyAst, expected: str) -> None:
    assert wdk_chat_name(ast, _WDK_ID) == expected
