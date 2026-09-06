"""Unit tests for conversation-title generation."""

from __future__ import annotations

from typing import cast

import pytest

from pathfinder.ai.conversation.title_generator import (
    MAX_TITLE_CHARS,
    MAX_TITLE_WORDS,
    _fallback_title,
    _trim_title,
    generate_conversation_title,
)
from pathfinder.assistants.pathfinder_spec import build_pathfinder_spec

MOCK_MODEL = build_pathfinder_spec().build_mock_model


class TestFallbackTitle:
    def test_empty_string_returns_default(self) -> None:
        assert _fallback_title("") == "New conversation"
        assert _fallback_title("   ") == "New conversation"

    def test_short_message_returned_verbatim(self) -> None:
        assert _fallback_title("hello world") == "hello world"

    def test_collapses_whitespace(self) -> None:
        assert _fallback_title("  hello   world\t") == "hello world"

    def test_long_message_is_truncated_with_ellipsis(self) -> None:
        msg = "x" * (MAX_TITLE_CHARS + 50)
        out = _fallback_title(msg)
        assert len(out) == MAX_TITLE_CHARS
        assert out.endswith("\u2026")


class TestTrimTitle:
    def test_strips_wrapping_quotes(self) -> None:
        assert _trim_title('"Plasmodium liver genes"') == "Plasmodium liver genes"

    def test_strips_trailing_punctuation(self) -> None:
        assert _trim_title("Toxoplasma IFN response.") == "Toxoplasma IFN response"

    def test_collapses_internal_whitespace(self) -> None:
        assert _trim_title("Malaria  \t drug targets") == "Malaria drug targets"

    def test_truncates_to_max_words(self) -> None:
        out = _trim_title("one two three four five six seven eight nine")
        assert out.split(" ") == [
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
        ]
        assert len(out.split(" ")) == MAX_TITLE_WORDS

    def test_truncates_to_max_chars(self) -> None:
        out = _trim_title("a" * 100)
        assert len(out) == MAX_TITLE_CHARS
        assert out.endswith("\u2026")


class TestGenerateConversationTitle:
    @pytest.mark.asyncio
    async def test_empty_message_short_circuits_to_default(self) -> None:
        assert await generate_conversation_title("", MOCK_MODEL) == "New conversation"
        assert (
            await generate_conversation_title("   ", MOCK_MODEL) == "New conversation"
        )

    @pytest.mark.asyncio
    async def test_unknown_provider_falls_back(self) -> None:
        # No cloud key is required for this path — the catalog lookup fails
        # because "mock" (when not configured as smallest) has no entry for
        # some providers. We use a deliberately absurd provider literal cast
        # through ModelProvider to trigger LookupError → fallback path.
        from assistant_core.platform.types import ModelProvider  # noqa: PLC0415

        bogus = cast("ModelProvider", "does-not-exist")
        out = await generate_conversation_title(
            "Find malaria genes",
            MOCK_MODEL,
            provider=bogus,
        )
        assert out == "Find malaria genes"
