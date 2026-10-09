"""Application configuration using pydantic-settings."""

import base64
import binascii
import tomllib
from functools import cached_property, lru_cache
from ipaddress import IPv4Address
from pathlib import Path
from typing import Literal, Self, get_args, get_origin
from urllib.parse import urlsplit

from assistant_core.platform.config import RuntimeSettings, use_settings_source
from assistant_core.platform.pydantic_base import computed
from assistant_core.platform.types import ModelProvider, TierName
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from veupathdb import (
    VEuPathDBSettings,
    use_veupathdb_settings_source,
)
from veupathdb.wdk import load_sites_config
from veupathdb_mcp import ServiceTokenRegistry
from veupathdb_mcp.embeddings import EmbeddingSettings, use_embedding_settings_source
from veupathdb_mcp.settings import McpSettings, use_mcp_settings_source

from pathfinder.platform.identity import (
    INTERNAL_STRATEGY_NAME_PREFIX,
    VEUPATHDB_USER_AGENT,
)
from pathfinder.platform.model_catalog import DEFAULT_MODEL_ID
from pathfinder.platform.paths import API_DIR, REPO_ROOT
from pathfinder.platform.provider_key_cipher import SECRET_BYTES, ProviderKeyCipher

BASE_PATH = "/pathfinder"
_LOCAL_PUBLIC_BASE_URL = f"http://localhost:3000{BASE_PATH}"

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

    # A key declared with no value is the default, so an env file may name
    # every key its example declares.
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(API_DIR / ".env")),
        env_ignore_empty=True,
    )

    # API
    api_host: str = Field(default_factory=lambda: str(IPv4Address(0)))
    api_port: int = 8000
    api_env: Literal["development", "staging", "production", "test"] = "production"
    api_secret_key: str = Field(default="", repr=False)
    api_docs_enabled: bool = True
    public_base_url: str = _LOCAL_PUBLIC_BASE_URL

    anthropic_api_key: str = Field(default="", repr=False)
    gemini_api_key: str = Field(default="", repr=False)

    # Base64url of 32 random bytes. Researchers' provider keys are sealed under
    # it; empty means this deployment accepts no personal key.
    provider_key_encryption_key: str = Field(default="", repr=False)

    # Ollama (local models via OpenAI-compatible API)
    ollama_base_url: str = ""

    # Provider plus tier resolve to the per-phase models.
    default_provider: ModelProvider = "openai"
    default_tier: TierName = "default"

    # VEuPathDB
    pathfinder_site: str = "veupathdb"
    wdk_dev_email: str = Field(default="", repr=False)
    wdk_dev_password: SecretStr = SecretStr("")
    # The client's default names no product. Every helper strategy already in a
    # researcher's account carries this prefix, so it is what a run matches.
    veupathdb_internal_strategy_name_prefix: str = INTERNAL_STRATEGY_NAME_PREFIX
    veupathdb_user_agent: str = VEUPATHDB_USER_AGENT
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

    lead_turn_token_limit: int = Field(
        default=600_000,
        ge=1,
        description=(
            "Tokens the Lead's own run may spend in one turn. A sub-agent pass "
            "the Lead dispatches carries a ceiling of its own and is not "
            "counted here. A run that reaches it ends with a reply that says so."
        ),
    )

    # Prompt-injection screening, and the model one judgement runs on.
    input_screening_enabled: bool = True
    input_screening_model: str = DEFAULT_MODEL_ID

    # Background worker
    worker_concurrency: int = Field(
        default=4,
        ge=1,
        description="Number of jobs the Procrastinate worker runs in parallel.",
    )
    metrics_port: int = Field(
        default=9100,
        ge=0,
        le=65535,
        description="Port this process publishes its Prometheus series on; 0 publishes none.",
    )
    metrics_addr: str = Field(
        default_factory=lambda: str(IPv4Address(0)),
        description="Address the Prometheus series server binds.",
    )

    # The OTLP exporter reads the standard OTEL_EXPORTER_OTLP_* variables itself.
    otel_include_content: bool = Field(
        default=False,
        description="Export prompts, completions, and tool arguments in agent traces.",
    )

    # The Langfuse project: the OTLP ingress header, scores and product events.
    langfuse_secret_key: str = Field(default="", repr=False)
    langfuse_public_key: str = Field(default="", repr=False)
    langfuse_host: str = ""

    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    cors_origin_regex: str | None = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    # Default monthly usage quota in USD. The `users` row can override it.
    pathfinder_user_monthly_cost_limit_usd: float = 20.0

    @computed
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.api_env == "development"

    @property
    def offers_dev_site_login(self) -> bool:
        """Development with the dev account set mounts the site sign-in route."""
        return (
            self.is_development
            and bool(self.wdk_dev_email.strip())
            and bool(self.wdk_dev_password.get_secret_value())
        )

    def deployment_credential(self, provider: ModelProvider) -> str:
        """The key, or for ollama the base url, the deployment reaches a provider by."""
        match provider:
            case "openai":
                return self.openai_api_key
            case "anthropic":
                return self.anthropic_api_key
            case "google":
                return self.gemini_api_key
            case "ollama":
                return self.ollama_base_url
            case "mock":
                return ""

    @property
    def deployment_providers(self) -> frozenset[ModelProvider]:
        """The providers this deployment pays for.

        The mock answers for every provider, so a mock deployment pays for all.
        """
        every: tuple[ModelProvider, ...] = get_args(ModelProvider.__value__)
        if self.pathfinder_chat_provider.strip().lower() == "mock":
            return frozenset(every)
        return frozenset(p for p in every if self.deployment_credential(p).strip())

    @property
    def has_llm_configuration(self) -> bool:
        """Check whether at least one model backend is configured."""
        return bool(self.deployment_providers)

    @property
    def provider_key_cipher(self) -> ProviderKeyCipher | None:
        """The seal for researchers' keys, or None when the deployment takes none."""
        encoded = self.provider_key_encryption_key.strip()
        if not encoded:
            return None
        try:
            secret = base64.urlsafe_b64decode(encoded.encode())
        except binascii.Error, ValueError:
            secret = b""
        if len(secret) != SECRET_BYTES:
            msg = (
                "PROVIDER_KEY_ENCRYPTION_KEY must be the base64url encoding of "
                f"{SECRET_BYTES} random bytes."
            )
            raise ValueError(msg)
        return ProviderKeyCipher(secret=secret)

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

    @field_validator("public_base_url")
    @classmethod
    def _absolute_without_a_trailing_slash(cls, url: str) -> str:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            msg = f"PUBLIC_BASE_URL={url} is not an absolute http(s) URL with a host."
            raise ValueError(msg)
        return url.rstrip("/")

    @model_validator(mode="after")
    def _production_names_its_public_address(self) -> Self:
        if (
            self.api_env == "production"
            and self.public_base_url == _LOCAL_PUBLIC_BASE_URL
        ):
            msg = (
                "PUBLIC_BASE_URL must be set to the public address of PathFinder "
                f"under API_ENV=production, not {_LOCAL_PUBLIC_BASE_URL}."
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _site_is_in_the_sites_file(self) -> Self:
        if not (self.veupathdb_sites_config or "").strip():
            msg = "VEUPATHDB_SITES_CONFIG must name the sites file this process serves."
            raise ValueError(msg)
        sites = load_sites_config(self.veupathdb_sites_config).sites
        if self.pathfinder_site not in sites:
            msg = f"PATHFINDER_SITE={self.pathfinder_site} is not in the sites file."
            raise ValueError(msg)
        return self

    def model_post_init(self, _context: object, /) -> None:
        """Validate settings after initialization."""
        self._validate_required_settings()
        self._validate_chat_provider()
        self._validate_service_tokens()
        self._validate_langfuse_settings()
        _ = self.provider_key_cipher

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
            TomlConfigSettingsSource(settings_cls, API_DIR / "config.toml"),
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


use_settings_source(get_settings)
use_veupathdb_settings_source(get_settings)
use_mcp_settings_source(get_settings)
use_embedding_settings_source(get_settings)
