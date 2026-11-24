import pytest
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyAst,
    StrategyStepNode,
)

from strategist.services.conversations.responses import derive_steps_from_strategy_ast

_WDK_DEFAULT = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"


@pytest.mark.parametrize(
    ("search_name", "display_name"),
    [(COMBINE_SEARCH_NAME, None), (_WDK_DEFAULT, _WDK_DEFAULT)],
)
def test_an_unnamed_combine_shows_its_operators_name_and_no_search(
    search_name: str, display_name: str | None
) -> None:
    combine = StrategyStepNode.model_validate(
        {
            "searchName": search_name,
            "displayName": display_name,
            "primaryInput": {"searchName": "GenesByText"},
            "secondaryInput": {"searchName": "GenesByTaxon"},
            "operator": CombineOp.MINUS,
        }
    )
    ast = StrategyAst(record_type="transcript", root=combine)

    resp = derive_steps_from_strategy_ast(ast)[0]

    assert (resp.search_name, resp.display_name) == (None, "Minus")


def test_search_step_keeps_search_name_as_display_name() -> None:
    leaf = StrategyStepNode(search_name="GenesByText")
    ast = StrategyAst(record_type="transcript", root=leaf)

    resp = derive_steps_from_strategy_ast(ast)[0]

    assert resp.display_name == "GenesByText"
