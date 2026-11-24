from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from assistant_core.persistence.models import Conversation

from strategist.domain.unread import Unread
from strategist.persistence.models import ConversationStrategyView
from strategist.platform.errors import AppError, ErrorCode
from strategist.services.conversations.responses import build_conversation_response
from strategist.services.strategies.session_factory import (
    refuse_a_build_on_an_unreadable_plan,
    thread_strategy_session,
)

_THREAD = UUID("6f1c2e0a-0000-4000-8000-000000000003")
_UNREADABLE = {
    "recordType": "transcript",
    "root": {
        "id": "step_root",
        "searchName": "__combine__",
        "operator": "INTERSECT",
        "primaryInput": {"id": "step_a", "searchName": "GenesByText"},
        "secondaryInput": {"id": "step_a", "searchName": "GenesByText"},
    },
}
_REASON = (
    f"conversation {_THREAD} holds a strategy_ast that does not parse: root: Value "
    "error, combine step cannot use the same step on both inputs "
    "(stepId='step_a'); use a single leaf or combine with a different step"
)


def _thread() -> tuple[Conversation, ConversationStrategyView]:
    conversation = Conversation(
        id=_THREAD,
        user_id=UUID("6f1c2e0a-0000-4000-8000-000000000004"),
        site_id="plasmodb",
        name="kinases",
        assistant_id="strategist",
        created_at=datetime(2026, 11, 24, tzinfo=UTC),
        updated_at=datetime(2026, 11, 24, tzinfo=UTC),
    )
    strategy = ConversationStrategyView(strategy_ast=_UNREADABLE)
    return conversation, strategy


def test_a_turn_opens_on_an_unreadable_plan_and_says_so() -> None:
    session = thread_strategy_session("plasmodb", *_thread())

    assert (session.get_graph(None), session.unreadable) == (
        None,
        Unread(reason=_REASON),
    )


def test_a_build_on_an_unreadable_plan_is_refused() -> None:
    session = thread_strategy_session("plasmodb", *_thread())

    with pytest.raises(AppError) as refused:
        refuse_a_build_on_an_unreadable_plan(session)

    assert (refused.value.code, refused.value.detail) == (
        ErrorCode.STRATEGY_AST_CORRUPT,
        _REASON,
    )


def test_the_detail_view_shows_the_plan_unreadable_with_its_reason() -> None:
    conversation, strategy = _thread()

    shown = build_conversation_response(conversation, strategy, mode="auto")

    assert (shown.steps, shown.strategy_unreadable) == (
        [],
        (
            "root: Value error, combine step cannot use the same step on both "
            "inputs (stepId='step_a'); use a single leaf or combine with a "
            "different step"
        ),
    )
