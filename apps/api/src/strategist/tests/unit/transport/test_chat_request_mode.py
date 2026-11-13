from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from strategist.ai.conversation.request_body import ChatRequestBody


def test_a_body_without_mode_is_auto() -> None:
    assert (
        ChatRequestBody.model_validate({"conversationId": str(uuid4())}).mode == "auto"
    )


def test_each_mode_is_read() -> None:
    for mode in ("auto", "explore", "build"):
        body = ChatRequestBody.model_validate(
            {"conversationId": str(uuid4()), "mode": mode}
        )
        assert body.mode == mode


def test_the_retired_strategy_mode_is_refused() -> None:
    with pytest.raises(ValidationError, match="mode"):
        ChatRequestBody.model_validate(
            {"conversationId": str(uuid4()), "mode": "strategy"}
        )
