from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyAst,
    StrategyStepNode,
)

from pathfinder.services.strategies.schemas import step_response_from_strategy_ast


def test_combine_step_serializes_friendly_label_not_sentinel() -> None:
    combine = StrategyStepNode.model_validate(
        {
            "primaryInput": {"searchName": "GenesByText"},
            "secondaryInput": {"searchName": "GenesByTaxon"},
            "operator": CombineOp.INTERSECT,
        }
    )
    ast = StrategyAst(record_type="transcript", root=combine)

    resp = step_response_from_strategy_ast(ast, combine)

    assert resp.search_name == COMBINE_SEARCH_NAME
    assert resp.display_name == "Combine"


def test_search_step_keeps_search_name_as_display_name() -> None:
    leaf = StrategyStepNode(search_name="GenesByText")
    ast = StrategyAst(record_type="transcript", root=leaf)

    resp = step_response_from_strategy_ast(ast, leaf)

    assert resp.display_name == "GenesByText"
