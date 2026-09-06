"""Tests for the typed payload models that background jobs take."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from veupathdb.auth_context import veupathdb_auth_token_ctx

from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.ai.graph._llm_capture import capture_llm
from pathfinder.jobs.payloads import (
    ChatTurnPayload,
    DurableTaskPayload,
)


def _body() -> ChatRequestBody:
    return ChatRequestBody.model_validate(
        {
            "conversationId": str(uuid4()),
            "messages": [
                {
                    "id": str(uuid4()),
                    "role": "user",
                    "parts": [{"type": "text", "text": "hi"}],
                },
            ],
            "siteId": "plasmodb",
        },
    )


class TestChatTurnPayload:
    def test_roundtrips_with_token_intact(self) -> None:
        """The token survives a JSON round trip without masking."""
        payload = ChatTurnPayload(
            body=_body(),
            user_id=uuid4(),
            turn_id=uuid4(),
            veupathdb_auth_token="cookie-value-abc123",
        )

        serialized = json.loads(payload.model_dump_json(by_alias=True))
        restored = ChatTurnPayload.model_validate(serialized)

        assert restored.veupathdb_auth_token == "cookie-value-abc123"
        assert restored.user_id == payload.user_id
        assert restored.turn_id == payload.turn_id

    def test_token_optional_defaults_to_none(self) -> None:
        payload = ChatTurnPayload(
            body=_body(),
            user_id=uuid4(),
            turn_id=uuid4(),
        )
        assert payload.veupathdb_auth_token is None

    def test_forbids_unknown_keys(self) -> None:
        """The schema is strict, so an extra key fails validation."""
        with pytest.raises(ValidationError):
            ChatTurnPayload.model_validate(
                {
                    "body": _body().model_dump(by_alias=True, mode="json"),
                    "user_id": str(uuid4()),
                    "turn_id": str(uuid4()),
                    "rogue_field": "x",
                },
            )

    def test_model_dump_mode_json_is_jsonable(self) -> None:
        """The job runner serializes arguments with json.dumps, so the dump must
        hold only JSON types."""
        payload = ChatTurnPayload(
            body=_body(),
            user_id=uuid4(),
            turn_id=uuid4(),
            veupathdb_auth_token="tok",
        )
        dumped = payload.model_dump(mode="json", by_alias=True)
        json.dumps(dumped)


class TestDurableTaskPayload:
    def test_roundtrips_with_token(self) -> None:
        payload = DurableTaskPayload(
            task_id=uuid4(),
            thread_id=uuid4(),
            args={"args": [], "kwargs": {"x": 5}},
            veupathdb_auth_token="cookie-xyz",
        )
        serialized = json.loads(payload.model_dump_json(by_alias=True))
        restored = DurableTaskPayload.model_validate(serialized)

        assert restored.veupathdb_auth_token == "cookie-xyz"
        assert restored.args == {"args": [], "kwargs": {"x": 5}}

    def test_token_optional(self) -> None:
        payload = DurableTaskPayload(
            task_id=uuid4(),
            thread_id=uuid4(),
            args={},
        )
        assert payload.veupathdb_auth_token is None

    def test_forbids_unknown_keys(self) -> None:
        with pytest.raises(ValidationError):
            DurableTaskPayload.model_validate(
                {
                    "task_id": str(uuid4()),
                    "thread_id": str(uuid4()),
                    "args": {},
                    "rogue": True,
                },
            )


class TestChatTurnPayloadFromContext:
    """The context constructor reads the current auth token and puts it on the payload,
    so the token crosses the boundary into the worker."""

    def test_captures_token_from_ctxvar(self) -> None:
        body = _body()
        user_id = uuid4()
        turn_id = uuid4()
        reset = veupathdb_auth_token_ctx.set("cookie-from-request")
        try:
            payload = ChatTurnPayload.from_context(
                body=body,
                user_id=user_id,
                turn_id=turn_id,
            )
        finally:
            veupathdb_auth_token_ctx.reset(reset)
        assert payload.veupathdb_auth_token == "cookie-from-request"
        assert payload.user_id == user_id
        assert payload.turn_id == turn_id

    def test_captures_none_when_ctxvar_unset(self) -> None:
        assert veupathdb_auth_token_ctx.get() is None
        payload = ChatTurnPayload.from_context(
            body=_body(),
            user_id=uuid4(),
            turn_id=uuid4(),
        )
        assert payload.veupathdb_auth_token is None


class TestDurableTaskPayloadFromContext:
    def test_captures_token_from_ctxvar(self) -> None:
        reset = veupathdb_auth_token_ctx.set("durable-cookie")
        try:
            payload = DurableTaskPayload.from_context(
                task_id=uuid4(),
                thread_id=uuid4(),
                args={"args": [], "kwargs": {}},
            )
        finally:
            veupathdb_auth_token_ctx.reset(reset)
        assert payload.veupathdb_auth_token == "durable-cookie"

    def test_captures_none_when_ctxvar_unset(self) -> None:
        assert veupathdb_auth_token_ctx.get() is None
        payload = DurableTaskPayload.from_context(
            task_id=uuid4(),
            thread_id=uuid4(),
            args={},
        )
        assert payload.veupathdb_auth_token is None


class TestCaptureDirThreading:
    """A task deferred inside a capture block inherits the run directory. A task
    deferred outside one carries no directory."""

    def test_chat_turn_payload_carries_capture_dir_roundtrip(self) -> None:
        payload = ChatTurnPayload(
            body=_body(),
            user_id=uuid4(),
            turn_id=uuid4(),
            capture_dir="/data/pf-runs/x/turn1",
        )
        restored = ChatTurnPayload.model_validate(
            json.loads(payload.model_dump_json(by_alias=True))
        )
        assert restored.capture_dir == "/data/pf-runs/x/turn1"

    def test_durable_payload_inherits_active_capture_dir(self, tmp_path) -> None:
        with capture_llm(tmp_path):
            payload = DurableTaskPayload.from_context(
                task_id=uuid4(),
                thread_id=uuid4(),
                args={"args": [], "kwargs": {}},
            )
        assert payload.capture_dir == str(tmp_path)

    def test_durable_payload_capture_dir_none_outside_block(self) -> None:
        payload = DurableTaskPayload.from_context(
            task_id=uuid4(),
            thread_id=uuid4(),
            args={},
        )
        assert payload.capture_dir is None
