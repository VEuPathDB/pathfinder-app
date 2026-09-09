"""The conversation insert seam names the assistant on every row."""

from __future__ import annotations

import inspect

from pathfinder.persistence.repositories.conversation import ConversationRepository


def test_create_takes_a_required_assistant_id() -> None:
    """A caller that omits the assistant fails to type-check, not at runtime."""
    parameter = inspect.signature(ConversationRepository.create).parameters[
        "assistant_id"
    ]

    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.annotation == "str"
