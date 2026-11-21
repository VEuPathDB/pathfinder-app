from __future__ import annotations

from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from strategist.persistence.repositories.conversation_update import (
    ConversationUpdate,
)


def test_an_empty_update_writes_no_strategy_value() -> None:
    assert ConversationUpdate(name="kinases").strategy_values() == {}


def test_a_simple_field_is_written_when_it_holds_a_value() -> None:
    upd = ConversationUpdate(
        record_type="transcript",
        wdk_strategy_created_here=False,
        is_saved=True,
        step_count=0,
        gene_set_auto_imported=False,
        imported_saved_strategy_ids=[7, 9],
    )

    assert upd.strategy_values() == {
        "record_type": "transcript",
        "wdk_strategy_created_here": False,
        "is_saved": True,
        "step_count": 0,
        "gene_set_auto_imported": False,
        "imported_saved_strategy_ids": [7, 9],
    }


def test_a_flagged_field_is_written_only_under_its_flag() -> None:
    upd = ConversationUpdate(
        wdk_strategy_id=11,
        estimated_size=None,
        estimated_size_set=True,
        gene_set_id="gs-1",
        generated_name_seed=None,
        generated_name_seed_set=True,
    )

    assert upd.strategy_values() == {
        "estimated_size": None,
        "generated_name_seed": None,
    }


def test_a_flagged_field_carries_its_value() -> None:
    seed = {"step_1": {"text_expression": "kinase"}}
    upd = ConversationUpdate(
        wdk_strategy_id=11,
        wdk_strategy_id_set=True,
        gene_set_id="gs-1",
        gene_set_id_set=True,
        generated_name_seed=seed,
        generated_name_seed_set=True,
    )

    assert upd.strategy_values() == {
        "wdk_strategy_id": 11,
        "gene_set_id": "gs-1",
        "generated_name_seed": seed,
    }


def test_the_strategy_is_written_in_its_wire_shape() -> None:
    ast = StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_1",
            search_name="GenesByText",
            parameters={"text_expression": StringValue(value="kinase")},
        ),
    )

    assert ConversationUpdate(strategy_ast=ast).strategy_values() == {
        "strategy_ast": ast.model_dump(by_alias=True, exclude_none=True, mode="json")
    }
