"""Two UAT gaps in what the conversation DTOs carry.

1. The saved-strategy library lists name + step count only, so the description
   the "Save as reusable strategy" dialog collects is write-only. The list view
   is built by ``build_conversation_summary``, which never read it back.
2. Nothing on either DTO identified *which* strategy state a response describes,
   so the chat transcript could not tell that its quoted counts predate a later
   edit.
"""

from datetime import UTC, datetime
from uuid import uuid4

from assistant_core.persistence.models import Conversation
from veupathdb.domain.strategy import StrategyAst

from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.services.conversations.responses import (
    build_conversation_response,
    build_conversation_summary,
)


def _ast(fold_change: str = "1", description: str | None = None) -> StrategyAst:
    return StrategyAst.model_validate(
        {
            "recordType": "transcript",
            "description": description,
            "root": {
                "id": "step_a",
                "searchName": "GenesByRNASeqEvidence",
                "parameters": {
                    "fold_change": {"type": "string", "value": fold_change},
                },
            },
        },
    )


def _thread(ast: StrategyAst | None) -> tuple[Conversation, ConversationStrategyView]:
    now = datetime.now(UTC)
    conversation = Conversation(
        id=uuid4(),
        user_id=uuid4(),
        assistant_id="pathfinder",
        site_id="plasmodb",
        name="Gametocyte markers",
        created_at=now,
        updated_at=now,
    )
    strategy = ConversationStrategyView(
        is_saved=True,
        step_count=1,
        gene_set_auto_imported=False,
        imported_saved_strategy_ids=[],
        estimated_size=None,
        strategy_ast=(
            ast.model_dump(by_alias=True, exclude_none=True, mode="json")
            if ast is not None
            else {}
        ),
    )
    return conversation, strategy


def test_summary_surfaces_the_saved_strategy_description() -> None:
    thread = _thread(_ast(description="Reusable gametocyte baseline."))
    assert (
        build_conversation_summary(*thread).description
        == "Reusable gametocyte baseline."
    )


def test_summary_description_is_none_without_one() -> None:
    assert build_conversation_summary(*_thread(_ast())).description is None


def test_summary_survives_a_conversation_with_no_strategy() -> None:
    summary = build_conversation_summary(*_thread(None))
    assert summary.description is None
    assert summary.strategy_revision == ""


def test_both_dtos_report_the_same_revision() -> None:
    thread = _thread(_ast())
    expected = strategy_revision(_ast())
    assert build_conversation_summary(*thread).strategy_revision == expected
    assert build_conversation_response(*thread).strategy_revision == expected


def test_editing_a_parameter_moves_the_revision() -> None:
    before = build_conversation_response(*_thread(_ast("1"))).strategy_revision
    after = build_conversation_response(*_thread(_ast("2"))).strategy_revision
    assert before != after
