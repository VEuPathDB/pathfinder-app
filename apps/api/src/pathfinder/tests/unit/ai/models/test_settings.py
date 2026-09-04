from typing import get_args

import pytest
from assistant_core.platform.types import ModelProvider
from pydantic_ai.models import infer_model
from pydantic_ai.models.openai import OpenAIResponsesModel

from pathfinder.ai.models.catalog import get_model_catalog
from pathfinder.ai.models.settings import build_model_settings, model_provider


class TestModelProvider:
    def test_openai(self) -> None:
        assert model_provider("openai:gpt-4.1-mini") == "openai"

    def test_anthropic(self) -> None:
        assert model_provider("anthropic:claude-opus-4-6") == "anthropic"

    def test_google(self) -> None:
        assert model_provider("google:gemini-2.5-pro") == "google"


class TestOpenAIIdsResolveToResponsesApi:
    """We hand pydantic-ai our stable ``openai:`` ids unchanged. That is only
    correct because pydantic-ai v2 resolves a bare ``openai:`` prefix to the
    Responses API (v1 resolved it to Chat Completions, which is why a rewrite
    shim used to exist here). Pin the assumption so a regression is loud."""

    def test_bare_openai_prefix_is_the_responses_api(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        assert isinstance(infer_model("openai:gpt-5-mini"), OpenAIResponsesModel)

    def test_holds_across_the_catalog_openai_families(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        for model in ("gpt-4.1", "gpt-5", "gpt-5.4", "o3", "o4-mini"):
            assert isinstance(infer_model(f"openai:{model}"), OpenAIResponsesModel)


class TestBuildModelSettings:
    def test_anthropic_enables_caching(self) -> None:
        data = dict(build_model_settings("anthropic:claude-opus-4-6"))
        assert data["anthropic_cache_instructions"] is True
        assert data["anthropic_cache_tool_definitions"] is True
        assert data["anthropic_cache_messages"] is True

    def test_anthropic_caching_composes_with_thinking(self) -> None:
        data = dict(build_model_settings("anthropic:claude-opus-4-6", thinking="high"))
        assert data["anthropic_cache_instructions"] is True
        assert data["thinking"] == "high"

    def test_openai_thinking_applied(self) -> None:
        data = dict(build_model_settings("openai:gpt-5.4", thinking="high"))
        assert data["thinking"] == "high"

    def test_openai_caching_is_automatic_no_flags(self) -> None:
        # OpenAI prompt caching is automatic; we don't set anthropic flags on it.
        data = dict(build_model_settings("openai:gpt-4.1-mini"))
        assert "anthropic_cache_instructions" not in data

    def test_google_thinking_applied(self) -> None:
        data = dict(build_model_settings("google:gemini-2.5-pro", thinking="medium"))
        assert data["thinking"] == "medium"

    def test_thinking_none_omitted(self) -> None:
        data = dict(build_model_settings("openai:gpt-4.1-mini", thinking="none"))
        assert "thinking" not in data

    def test_thinking_default_omitted(self) -> None:
        data = dict(build_model_settings("openai:gpt-4.1-mini"))
        assert "thinking" not in data


class TestEveryRequestCarriesATimeout:
    """A provider request that never returns must fail instead of hanging."""

    def test_openai_carries_the_timeout(self) -> None:
        assert build_model_settings("openai:gpt-5.6-luna")["timeout"] == 900

    def test_anthropic_carries_the_timeout(self) -> None:
        assert build_model_settings("anthropic:claude-opus-4-6")["timeout"] == 900

    def test_google_carries_the_timeout(self) -> None:
        assert build_model_settings("google:gemini-2.5-pro")["timeout"] == 900

    def test_timeout_survives_every_thinking_effort(self) -> None:
        for effort in ("none", "low", "medium", "high"):
            for model in ("openai:gpt-5.6-luna", "anthropic:claude-opus-4-6"):
                settings = build_model_settings(model, thinking=effort)

                assert settings["timeout"] == 900, (model, effort)

    def test_timeout_does_not_disturb_provider_settings(self) -> None:
        anthropic = build_model_settings("anthropic:claude-opus-4-6", thinking="high")
        openai = build_model_settings("openai:gpt-5.6-luna", thinking="high")

        assert anthropic.get("anthropic_cache_instructions") is True
        assert anthropic["thinking"] == "high"
        assert openai.get("openai_send_reasoning_ids") is False
        assert openai["thinking"] == "high"


class TestOpenAiItemIdsAreNotSentBack:
    """The Responses API validates item IDs we echo back; we rewrite history,
    so they never match.

    ``openai_send_reasoning_ids`` defaults to True for reasoning models and
    makes pydantic-ai send the IDs of reasoning, text and **function call**
    parts from history. pydantic-ai's own docs say to disable it when the
    history "does not match exactly what was received from the Responses API
    ... for example if you're using a history processor".

    Every one of our agents runs `pair_tool_calls` and
    `elide_consumed_tool_results`, so our history never matches byte for
    byte. Sending the IDs made OpenAI reject the request with
    "No tool invocation found for tool call ID ...", which is the crash seen
    on branching, reverting, cancel-then-send, and long tool loops.
    """

    def test_openai_does_not_send_item_ids(self) -> None:
        settings = build_model_settings("openai:gpt-5.6-luna")

        assert settings.get("openai_send_reasoning_ids") is False

    def test_it_is_disabled_regardless_of_thinking_effort(self) -> None:
        for effort in ("none", "low", "medium", "high"):
            settings = build_model_settings("openai:gpt-5.6-luna", thinking=effort)

            assert settings.get("openai_send_reasoning_ids") is False, effort

    def test_anthropic_is_untouched(self) -> None:
        # The setting is OpenAI-only; Anthropic keeps its cache flags.
        settings = build_model_settings("anthropic:claude-sonnet-5")

        assert "openai_send_reasoning_ids" not in settings
        assert settings.get("anthropic_cache_messages") is True

    def test_thinking_still_applied_for_openai(self) -> None:
        settings = build_model_settings("openai:gpt-5.6-luna", thinking="high")

        assert settings.get("thinking") == "high"
        assert settings.get("openai_send_reasoning_ids") is False


class TestEveryCatalogProviderHasItsOwnSettings:
    """A provider that falls through to another provider's settings carries
    flags its API never reads."""

    def test_google_carries_no_openai_flag(self) -> None:
        settings = build_model_settings("google:gemini-3.1-pro-preview")

        assert "openai_send_reasoning_ids" not in settings
        assert "anthropic_cache_messages" not in settings

    def test_google_still_carries_the_reasoning_effort(self) -> None:
        settings = build_model_settings(
            "google:gemini-3.1-pro-preview", thinking="high"
        )

        assert settings["thinking"] == "high"

    def test_ollama_carries_no_responses_api_flag(self) -> None:
        """Ollama speaks Chat Completions, where the flag does not exist."""
        settings = build_model_settings("ollama:qwen3")

        assert "openai_send_reasoning_ids" not in settings
        assert settings["timeout"] == 900

    def test_mock_carries_no_provider_flag(self) -> None:
        settings = build_model_settings("mock:deterministic")

        assert "openai_send_reasoning_ids" not in settings
        assert "anthropic_cache_messages" not in settings

    def test_an_unknown_provider_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no model settings"):
            build_model_settings("bedrock:nova-pro")

    def test_every_catalog_entry_resolves_to_settings(self) -> None:
        for entry in get_model_catalog():
            assert build_model_settings(entry.id)["timeout"] == 900, entry.id

    def test_the_provider_set_is_the_declared_one(self) -> None:
        """The settings table covers exactly the providers the type declares."""
        declared = sorted(get_args(ModelProvider.__value__))
        resolved = sorted(
            provider
            for provider in declared
            if build_model_settings(f"{provider}:x")["timeout"] == 900
        )

        assert resolved == declared
