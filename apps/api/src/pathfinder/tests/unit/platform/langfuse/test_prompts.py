"""Tests for Langfuse prompt management with local fallback."""

from unittest.mock import MagicMock, patch

import pytest
from langfuse.api.commons.errors.not_found_error import NotFoundError

from pathfinder.platform.langfuse.prompts import (
    load_prompt_result,
    seed_prompts,
)


class TestLoadPromptLocalFallback:
    """When Langfuse is disabled (returns None), prompts load from local files."""

    def test_loads_system_prompt_from_local(self) -> None:
        with patch(
            "pathfinder.platform.langfuse.prompts.get_langfuse",
            return_value=None,
        ):
            result = load_prompt_result("system").text
        assert len(result) > 100
        assert "VEuPathDB" in result

    def test_loads_safety_prompt_from_local(self) -> None:
        with patch(
            "pathfinder.platform.langfuse.prompts.get_langfuse",
            return_value=None,
        ):
            result = load_prompt_result("safety").text
        assert len(result) > 0

    def test_loads_site_hints_prompt_from_local(self) -> None:
        with patch(
            "pathfinder.platform.langfuse.prompts.get_langfuse",
            return_value=None,
        ):
            result = load_prompt_result("site-hints").text
        assert len(result) > 0

    def test_load_prompt_result_tracks_local_metadata(self) -> None:
        with patch(
            "pathfinder.platform.langfuse.prompts.get_langfuse",
            return_value=None,
        ):
            result = load_prompt_result("system")
        assert result.name == "system"
        assert result.source == "local"
        assert result.label == "production"
        assert result.version is None
        assert len(result.text) > 100


class TestLoadPromptLangfuseError:
    """When Langfuse client raises a caught error, falls back to local."""

    def test_falls_back_on_langfuse_api_error(self) -> None:
        mock_client = MagicMock()
        mock_client.get_prompt.side_effect = OSError("connection refused")
        with patch(
            "pathfinder.platform.langfuse.prompts.get_langfuse",
            return_value=mock_client,
        ):
            result = load_prompt_result("system").text
        assert len(result) > 100

    def test_falls_back_on_value_error(self) -> None:
        mock_client = MagicMock()
        mock_client.get_prompt.side_effect = ValueError("bad arg")
        with patch(
            "pathfinder.platform.langfuse.prompts.get_langfuse",
            return_value=mock_client,
        ):
            result = load_prompt_result("system").text
        assert len(result) > 100

    def test_falls_back_on_not_found_error(self) -> None:
        mock_client = MagicMock()
        mock_client.get_prompt.side_effect = NotFoundError(
            body={"message": "not found"}
        )
        with patch(
            "pathfinder.platform.langfuse.prompts.get_langfuse",
            return_value=mock_client,
        ):
            result = load_prompt_result("system").text
        assert len(result) > 100


class TestLoadPromptFromLangfuse:
    """When Langfuse client succeeds, returns its content."""

    def test_uses_langfuse_when_available(self) -> None:
        mock_prompt = MagicMock()
        mock_prompt.compile.return_value = "langfuse prompt content"
        mock_client = MagicMock()
        mock_client.get_prompt.return_value = mock_prompt
        with patch(
            "pathfinder.platform.langfuse.prompts.get_langfuse",
            return_value=mock_client,
        ):
            result = load_prompt_result("system").text
        assert result == "langfuse prompt content"
        mock_client.get_prompt.assert_called_once_with("system", label="production")

    def test_custom_label(self) -> None:
        mock_prompt = MagicMock()
        mock_prompt.compile.return_value = "staging content"
        mock_client = MagicMock()
        mock_client.get_prompt.return_value = mock_prompt
        with patch(
            "pathfinder.platform.langfuse.prompts.get_langfuse",
            return_value=mock_client,
        ):
            result = load_prompt_result("system", label="staging").text
        assert result == "staging content"
        mock_client.get_prompt.assert_called_once_with("system", label="staging")

    def test_load_prompt_result_returns_version_metadata(self) -> None:
        mock_prompt = MagicMock()
        mock_prompt.compile.return_value = "langfuse prompt content"
        mock_prompt.version = 7
        mock_client = MagicMock()
        mock_client.get_prompt.return_value = mock_prompt
        with patch(
            "pathfinder.platform.langfuse.prompts.get_langfuse",
            return_value=mock_client,
        ):
            result = load_prompt_result("system")
        assert result.name == "system"
        assert result.source == "langfuse"
        assert result.version == 7
        assert result.text == "langfuse prompt content"


class TestLoadPromptUnknownName:
    """Unknown prompt names raise ValueError."""

    def test_raises_value_error(self) -> None:
        with (
            patch(
                "pathfinder.platform.langfuse.prompts.get_langfuse",
                return_value=None,
            ),
            pytest.raises(ValueError, match="nonexistent"),
        ):
            load_prompt_result("nonexistent")


class TestSeedPrompts:
    """seed_prompts uploads local files to Langfuse."""

    def test_noop_when_langfuse_disabled(self) -> None:
        with patch(
            "pathfinder.platform.langfuse.prompts.get_langfuse",
            return_value=None,
        ):
            seed_prompts()  # Should not raise

    def test_seeds_missing_prompts(self) -> None:
        mock_client = MagicMock()
        # get_prompt raises NotFoundError for all names (they don't exist yet)
        mock_client.get_prompt.side_effect = NotFoundError(
            body={"message": "not found"}
        )
        with patch(
            "pathfinder.platform.langfuse.prompts.get_langfuse",
            return_value=mock_client,
        ):
            seed_prompts()

        seeded = [
            call_obj.kwargs["name"]
            for call_obj in mock_client.create_prompt.call_args_list
        ]
        assert seeded == ["system", "safety", "site-hints"]
        for call_obj in mock_client.create_prompt.call_args_list:
            assert call_obj.kwargs["type"] == "text"

    def test_skips_existing_prompts(self) -> None:
        mock_client = MagicMock()
        # get_prompt succeeds for all (prompts already exist)
        mock_client.get_prompt.return_value = MagicMock()
        with patch(
            "pathfinder.platform.langfuse.prompts.get_langfuse",
            return_value=mock_client,
        ):
            seed_prompts()

        mock_client.create_prompt.assert_not_called()

    def test_skips_seed_on_non_not_found_error(self) -> None:
        mock_client = MagicMock()
        mock_client.get_prompt.side_effect = OSError("connection refused")
        with patch(
            "pathfinder.platform.langfuse.prompts.get_langfuse",
            return_value=mock_client,
        ):
            seed_prompts()

        mock_client.create_prompt.assert_not_called()
