"""Application configuration using pydantic-settings."""

import tomllib
from functools import cached_property, lru_cache
from ipaddress import IPv4Address
from pathlib import Path
from typing import Literal, get_origin

from assistant_core.platform.config import RuntimeSettings, use_settings_source
from assistant_core.platform.types import ModelProvider, TierName
from pydantic import Field, computed_field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from veupathdb.settings import (
    VEuPathDBSettings,
    use_veupathdb_settings_source,
)
from veupathdb_mcp.embeddings.settings import (
    EmbeddingSettings,
    use_embedding_settings_source,
)
from veupathdb_mcp.service_tokens import ServiceTokenRegistry
from veupathdb_mcp.settings import McpSettings, use_mcp_settings_source

from pathfinder.platform.identity import INTERNAL_STRATEGY_NAME_PREFIX

_API_DIR = Path(__file__).resolve().parents[3]  # apps/api/
_REPO_ROOT = _API_DIR.parents[1]  # repo root
_MIN_API_SECRET_LENGTH = 32
_PLACEHOLDER_SECRET_MARKERS = (
    "dev-only",
    "change-me",
    "xxxx",
    "placeholder",
    "example",
)
_ALLOWED_CHAT_PROVIDERS = {"default", "mock"}


class TomlConfigSettingsSource(PydanticBaseSettingsSource):
    """Load settings from a TOML config file."""

    def __init__(self, settings_cls: type[BaseSettings], config_path: Path) -> None:
        super().__init__(settings_cls)
        path = config_path.resolve()

        if not path.exists():
            self._data: dict[str, object] = {}
        else:
            with path.open("rb") as handle:
                self._data = tomllib.load(handle)

    def _is_complex_field(self, field: object) -> bool:
        annotation = getattr(field, "annotation", None)
        origin = get_origin(annotation) or annotation
        return origin in (list, dict, set, tuple)

    def get_field_value(
        self, field: object, field_name: str
    ) -> tuple[object, str, bool]:
        value = self._data.get(field_name)
        if value is None:
            return None, field_name, False
        if self._is_complex_field(field):
            if isinstance(value, (str, bytes, bytearray)):
                return value, field_name, True
            return value, field_name, False
        return value, field_name, False

    def __call__(self) -> dict[str, object]:
        data: dict[str, object] = {}
        for field_name, field in self.settings_cls.model_fields.items():
            value, key, is_complex = self.get_field_value(field, field_name)
            if value is None:
                continue
            if not isinstance(value, (str, bytes, bytearray)):
                data[key] = value
                continue
            # A blank entry is no entry, the way a blank variable is to the env source.
            if not value:
                continue
            value = self.prepare_field_value(field_name, field, value, is_complex)
            if value is not None:
                data[key] = value
        return data


class Settings(RuntimeSettings, VEuPathDBSettings, McpSettings, EmbeddingSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), str(_API_DIR / ".env")),
    )

    # API
    api_host: str = Field(default_factory=lambda: str(IPv4Address(0)))
    api_port: int = 8000
    api_env: Literal["development", "staging", "production", "test"] = "production"
    api_secret_key: str = Field(default="", repr=False)
    api_docs_enabled: bool = True

    anthropic_api_key: str = Field(default="", repr=False)
    gemini_api_key: str = Field(default="", repr=False)

    # Ollama (local models via OpenAI-compatible API)
    ollama_base_url: str = ""

    # Provider plus tier resolve to the per-phase models.
    default_provider: ModelProvider = "openai"
    default_tier: TierName = "default"

    # VEuPathDB
    veupathdb_default_site: str = "veupathdb"
    # The client's default names no product. Every helper strategy already in a
    # researcher's account carries this prefix, so it is what a run matches.
    veupathdb_internal_strategy_name_prefix: str = INTERNAL_STRATEGY_NAME_PREFIX
    site_preload_timeout_seconds: int = Field(
        default=30,
        ge=1,
        description=(
            "Budget for one site's catalog load, at startup and on every retry. "
            "A site that does not answer inside it is degraded."
        ),
    )
    site_retry_interval_seconds: int = Field(
        default=60,
        ge=1,
        description="Seconds between two passes over the degraded sites.",
    )
    # Semantic Scholar
    s2_api_key: str = Field(default="", repr=False)

    # Application identities, as "app_id:secret[,app_id:secret...]".
    pathfinder_service_tokens: str = Field(default="", repr=False)

    # The two MCP endpoints this deployment's assistants call, and the
    # credential it presents at each. An empty URL admits nobody.
    pathfinder_wdk_mcp_url: str = ""
    pathfinder_wdk_mcp_token: str = Field(default="", repr=False)
    pathfinder_research_mcp_url: str = ""
    pathfinder_research_mcp_token: str = Field(default="", repr=False)

    # Conversation provider. "mock" gives deterministic offline runs.
    pathfinder_chat_provider: str = ""

    # Prompt-injection screening with the PIGuard ONNX model.
    piguard_enabled: bool = True
    piguard_model_dir: Path = Path("/app/models/piguard")

    # Background worker
    worker_concurrency: int = Field(
        default=4,
        ge=1,
        description="Number of jobs the Procrastinate worker runs in parallel.",
    )

    # Observability: SigNoz APM
    signoz_otel_endpoint: str | None = Field(
        default=None,
        description="SigNoz OTel Collector gRPC endpoint (e.g. http://signoz-otel-collector:4317). Unset = disabled.",
    )
    signoz_trace_otel_http_endpoint: str | None = Field(
        default=None,
        description=(
            "Optional SigNoz OTLP/HTTP traces endpoint "
            "(e.g. http://signoz-otel-collector:4318/v1/traces). "
            "When set, traces use HTTP while metrics/logs continue using SIGNOZ_OTEL_ENDPOINT."
        ),
    )

    otel_include_content: bool = Field(
        default=False,
        description="Export prompts, completions, and tool arguments in agent traces.",
    )

    # Langfuse observability. All three values are needed together.
    langfuse_secret_key: str = Field(default="", repr=False)
    langfuse_public_key: str = Field(default="", repr=False)
    langfuse_host: str = ""

    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    cors_origin_regex: str | None = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    # Default monthly usage quota in USD. The `users` row can override it.
    pathfinder_user_monthly_cost_limit_usd: float = 20.0

    @computed_field
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.api_env == "development"

    @property
    def has_llm_configuration(self) -> bool:
        """Check whether at least one non-mock model backend is configured."""
        return bool(
            self.openai_api_key.strip()
            or self.anthropic_api_key.strip()
            or self.gemini_api_key.strip()
            or self.ollama_base_url.strip()
        )

    def _validate_required_settings(self) -> None:
        missing: list[str] = []
        if not self.api_secret_key.strip():
            missing.append("API_SECRET_KEY")
        if not self.database_url.strip():
            missing.append("DATABASE_URL")
        if missing:
            joined = ", ".join(missing)
            msg = f"Missing required settings: {joined}."
            raise ValueError(msg)

        if len(self.api_secret_key) < _MIN_API_SECRET_LENGTH:
            msg = (
                f"API_SECRET_KEY must be at least {_MIN_API_SECRET_LENGTH} characters."
            )
            raise ValueError(msg)

        if self.api_env not in ("development", "test") and any(
            marker in self.api_secret_key.lower()
            for marker in _PLACEHOLDER_SECRET_MARKERS
        ):
            msg = (
                "API_SECRET_KEY must be set to a real secret in production and staging. "
                "Placeholder keys are not allowed."
            )
            raise ValueError(msg)

    def _validate_chat_provider(self) -> None:
        provider = self.pathfinder_chat_provider.strip().lower()
        if not provider:
            msg = (
                "PATHFINDER_CHAT_PROVIDER must be set explicitly to "
                "'default' or 'mock'."
            )
            raise ValueError(msg)
        if provider not in _ALLOWED_CHAT_PROVIDERS:
            allowed = ", ".join(sorted(_ALLOWED_CHAT_PROVIDERS))
            msg = f"PATHFINDER_CHAT_PROVIDER must be one of: {allowed}."
            raise ValueError(msg)
        self.pathfinder_chat_provider = provider

        if provider == "mock" and self.api_env != "test":
            msg = "PATHFINDER_CHAT_PROVIDER=mock is only allowed when API_ENV=test."
            raise ValueError(msg)
        if provider != "mock" and not self.has_llm_configuration:
            msg = (
                "PathFinder requires a configured model backend. Set at least one of "
                "OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, or OLLAMA_BASE_URL, "
                "or use the dedicated test profile with PATHFINDER_CHAT_PROVIDER=mock."
            )
            raise ValueError(msg)

    @cached_property
    def service_tokens(self) -> ServiceTokenRegistry:
        """The application identities, parsed once per settings instance."""
        return ServiceTokenRegistry.parse(self.pathfinder_service_tokens)

    def _validate_service_tokens(self) -> None:
        _ = self.service_tokens
        _ = self.mcp_service_tokens

    def _validate_langfuse_settings(self) -> None:
        langfuse_values = {
            "LANGFUSE_HOST": self.langfuse_host.strip(),
            "LANGFUSE_PUBLIC_KEY": self.langfuse_public_key.strip(),
            "LANGFUSE_SECRET_KEY": self.langfuse_secret_key.strip(),
        }
        configured_langfuse = [name for name, value in langfuse_values.items() if value]
        if 0 < len(configured_langfuse) < len(langfuse_values):
            joined = ", ".join(langfuse_values)
            msg = f"{joined} must be set together when Langfuse is enabled."
            raise ValueError(msg)

    def model_post_init(self, _context: object, /) -> None:
        """Validate settings after initialization."""
        self._validate_required_settings()
        self._validate_chat_provider()
        self._validate_service_tokens()
        self._validate_langfuse_settings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            TomlConfigSettingsSource(settings_cls, _API_DIR / "config.toml"),
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


use_settings_source(get_settings)
use_veupathdb_settings_source(get_settings)
use_mcp_settings_source(get_settings)
use_embedding_settings_source(get_settings)
