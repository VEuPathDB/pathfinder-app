"""Tests for Langfuse product action recording."""

from unittest.mock import MagicMock, patch

from pathfinder.platform.langfuse.actions import (
    ProductActionEvent,
    record_product_action,
)


def test_record_product_action_noop_when_langfuse_disabled() -> None:
    with patch(
        "pathfinder.platform.langfuse.actions.get_langfuse",
        return_value=None,
    ):
        record_product_action(
            ProductActionEvent(
                action="plan_approve",
                trace_id="trace-123",
                stream_id="stream-abc",
                strategy_id="strategy-abc",
                plan_id="plan-123",
            )
        )


def test_record_product_action_creates_event_with_trace_context() -> None:
    mock_client = MagicMock()
    with patch(
        "pathfinder.platform.langfuse.actions.get_langfuse",
        return_value=mock_client,
    ):
        record_product_action(
            ProductActionEvent(
                action="plan_suggest_changes",
                trace_id="trace-123",
                stream_id="stream-abc",
                strategy_id="strategy-abc",
                plan_id="plan-123",
                message_group_id="group-1",
                metadata={"source": "plan_panel", "param_edit_count": 2},
            )
        )

    mock_client.create_event.assert_called_once_with(
        trace_context={"trace_id": "trace-123"},
        name="product.plan_suggest_changes",
        input={
            "action": "plan_suggest_changes",
            "stream_id": "stream-abc",
            "strategy_id": "strategy-abc",
            "plan_id": "plan-123",
            "message_group_id": "group-1",
        },
        metadata={
            "stream_id": "stream-abc",
            "strategy_id": "strategy-abc",
            "plan_id": "plan-123",
            "message_group_id": "group-1",
            "source": "plan_panel",
            "param_edit_count": 2,
        },
    )


def test_record_product_action_handles_exception() -> None:
    mock_client = MagicMock()
    mock_client.create_event.side_effect = OSError("Network error")
    with patch(
        "pathfinder.platform.langfuse.actions.get_langfuse",
        return_value=mock_client,
    ):
        record_product_action(
            ProductActionEvent(
                action="undo_turn",
                stream_id="stream-err",
                entry_id="1709234567890-0",
            )
        )


def test_a_message_rating_carries_the_turn_s_usage() -> None:
    mock_client = MagicMock()
    with patch(
        "pathfinder.platform.langfuse.actions.get_langfuse",
        return_value=mock_client,
    ):
        record_product_action(
            ProductActionEvent(
                action="message_rated",
                stream_id="7b0c2f4e-1111-4111-8111-111111111111",
                metadata={
                    "rating": "dislike",
                    "conversationId": "3a9d0c6e-2222-4222-8222-222222222222",
                    "messageId": "7b0c2f4e-1111-4111-8111-111111111111",
                    "turnTraceId": "trace-9",
                    "totalTokens": 18342,
                    "costUsd": 0.0412,
                },
            )
        )

    call = mock_client.create_event.call_args.kwargs
    assert call["name"] == "product.message_rated"
    assert call["metadata"]["rating"] == "dislike"
    assert call["metadata"]["turnTraceId"] == "trace-9"
    assert call["metadata"]["totalTokens"] == 18342
    assert call["metadata"]["costUsd"] == 0.0412
    assert call["metadata"]["conversationId"] == "3a9d0c6e-2222-4222-8222-222222222222"
