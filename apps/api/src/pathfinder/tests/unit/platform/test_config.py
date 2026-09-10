from pathlib import Path

import pytest

from pathfinder.platform.config import Settings, TomlConfigSettingsSource


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "api_env": "test",
        "api_secret_key": "pathfinder-test-secret-key-1234567890",
        "database_url": "postgresql+asyncpg://postgres:postgres@db:5432/pathfinder",
        "pathfinder_chat_provider": "mock",
        "openai_api_key": "",
        "anthropic_api_key": "",
        "gemini_api_key": "",
        "ollama_base_url": "",
        "langfuse_host": "",
        "langfuse_public_key": "",
        "langfuse_secret_key": "",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_piguard_enabled_defaults_true() -> None:
    assert make_settings().piguard_enabled is True


def test_piguard_can_be_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIGUARD_ENABLED", "false")
    settings = Settings(
        api_env="test",
        api_secret_key="pathfinder-test-secret-key-1234567890",
        database_url="postgresql+asyncpg://postgres:postgres@db:5432/pathfinder",
        pathfinder_chat_provider="mock",
    )
    assert settings.piguard_enabled is False


def test_mock_provider_is_rejected_outside_development() -> None:
    with pytest.raises(
        ValueError,
        match="PATHFINDER_CHAT_PROVIDER=mock is only allowed",
    ):
        make_settings(api_env="production", pathfinder_chat_provider="mock")


def test_non_mock_mode_requires_real_model_backend() -> None:
    with pytest.raises(ValueError, match="configured model backend"):
        make_settings(pathfinder_chat_provider="default")


def test_ollama_configuration_counts_as_model_backend() -> None:
    settings = make_settings(
        pathfinder_chat_provider="default",
        ollama_base_url="http://ollama:11434/v1",
    )
    assert settings.has_llm_configuration is True


def test_partial_langfuse_configuration_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY "
            "must be set together"
        ),
    ):
        make_settings(langfuse_host="http://langfuse:3000")


def test_secret_must_be_long_enough() -> None:
    with pytest.raises(
        ValueError,
        match="API_SECRET_KEY must be at least 32 characters",
    ):
        make_settings(api_secret_key="too-short")


def test_placeholder_secret_allowed_in_test_env() -> None:
    settings = make_settings(api_secret_key="placeholder-secret-key-1234567890ab")
    assert settings.api_secret_key == "placeholder-secret-key-1234567890ab"


def test_placeholder_secret_rejected_in_production() -> None:
    with pytest.raises(
        ValueError,
        match="must be set to a real secret",
    ):
        make_settings(
            api_env="production",
            pathfinder_chat_provider="default",
            anthropic_api_key="real-anthropic-key",
            api_secret_key="placeholder-secret-key-1234567890ab",
        )


def test_empty_env_value_is_ignored_for_complex_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "")

    settings = Settings(
        _env_file=None,
        api_env="test",
        api_secret_key="pathfinder-test-secret-key-1234567890",
        database_url="postgresql+asyncpg://postgres:postgres@db:5432/pathfinder",
        pathfinder_chat_provider="mock",
        openai_api_key="",
        anthropic_api_key="",
        gemini_api_key="",
        ollama_base_url="",
        langfuse_host="",
        langfuse_public_key="",
        langfuse_secret_key="",
    )

    assert settings.cors_origins == ["http://localhost:3000"]


def test_pathfinder_chat_provider_must_be_explicit() -> None:
    with pytest.raises(
        ValueError,
        match="PATHFINDER_CHAT_PROVIDER must be set explicitly",
    ):
        make_settings(pathfinder_chat_provider="")


def test_worker_concurrency_defaults_to_four() -> None:
    assert make_settings().worker_concurrency == 4


def test_worker_concurrency_rejects_zero() -> None:
    with pytest.raises(ValueError, match="worker_concurrency"):
        make_settings(worker_concurrency=0)


def test_worker_concurrency_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKER_CONCURRENCY", "8")

    assert make_settings().worker_concurrency == 8


def test_service_tokens_are_unset_by_default() -> None:
    assert make_settings().pathfinder_service_tokens == ""


def test_a_service_token_without_a_separator_is_rejected_at_load() -> None:
    with pytest.raises(ValueError, match="application_id:secret"):
        make_settings(pathfinder_service_tokens="analytics-secret-0123456789abcdef")


def test_a_short_service_token_secret_is_rejected_at_load() -> None:
    with pytest.raises(ValueError, match="at least 32 characters"):
        make_settings(pathfinder_service_tokens="analytics:too-short")


def test_a_valid_service_token_setting_loads() -> None:
    settings = make_settings(
        pathfinder_service_tokens="analytics:analytics-secret-0123456789abcdef",
    )

    assert "analytics-secret" not in repr(settings)


def test_the_service_token_registry_is_parsed_once() -> None:
    settings = make_settings(
        pathfinder_service_tokens="analytics:analytics-secret-0123456789abcdef",
    )

    assert settings.service_tokens is settings.service_tokens
    assert (
        settings.service_tokens.application_for(
            "analytics-secret-0123456789abcdef",
        )
        == "analytics"
    )


def test_a_short_mcp_service_token_secret_is_rejected_at_load() -> None:
    with pytest.raises(ValueError, match="at least 32 characters"):
        make_settings(wdk_mcp_service_tokens="gene-page:too-short")


def test_the_mcp_service_token_registry_is_its_own() -> None:
    """A secret the MCP server accepts must not authenticate to the API."""
    settings = make_settings(
        wdk_mcp_service_tokens="gene-page:gene-page-secret-0123456789abcdef",
    )

    assert (
        settings.mcp_service_tokens.application_for(
            "gene-page-secret-0123456789abcdef",
        )
        == "gene-page"
    )
    assert settings.service_tokens.tokens == ()
    assert "gene-page-secret" not in repr(settings)


def test_the_service_token_registry_stays_out_of_the_serialized_settings() -> None:
    settings = make_settings(
        pathfinder_service_tokens="analytics:analytics-secret-0123456789abcdef",
    )

    assert "service_tokens" not in settings.model_dump()


def test_the_oauth_client_id_setting_is_gone() -> None:
    """Nothing reads it, and the audience claim is deliberately not checked."""
    assert "veupathdb_oauth_client_id" not in Settings.model_fields


def test_the_oauth_url_defaults_to_the_veupathdb_auth_server() -> None:
    assert make_settings().veupathdb_oauth_url == "https://auth.veupathdb.org"


def test_a_blank_oauth_url_in_the_environment_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The client reads a blank variable as the field default."""
    monkeypatch.setenv("VEUPATHDB_OAUTH_URL", "")

    assert make_settings().veupathdb_oauth_url == "https://auth.veupathdb.org"


def test_otel_include_content_defaults_false() -> None:
    assert make_settings().otel_include_content is False


def test_otel_include_content_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_INCLUDE_CONTENT", "true")

    assert make_settings().otel_include_content is True


def test_a_blank_toml_value_leaves_the_field_default_standing(
    tmp_path: Path,
) -> None:
    """A blank TOML entry is no entry, the way a blank variable is."""
    config = tmp_path / "config.toml"
    config.write_text(
        'veupathdb_default_site = ""\nlog_level = "DEBUG"\napi_port = 9001\n'
    )

    values = TomlConfigSettingsSource(Settings, config)()

    assert values == {"log_level": "DEBUG", "api_port": 9001}
