"""The catalog of selectable LLM models: cloud entries plus local entries from YAML."""

from functools import lru_cache
from typing import Any

import yaml
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import ModelProvider
from pydantic import BaseModel, ConfigDict, model_validator

from pathfinder.platform.config import _REPO_ROOT

__all__ = [
    "ModelEntry",
    "ModelProvider",
    "context_window_for",
    "get_model_catalog",
    "get_model_entry",
]


class ModelEntry(CamelModel):
    """One model in the catalog.

    The ID holds the provider and the model name, joined by a colon.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    description: str = ""
    supports_reasoning: bool = False
    context_size: int = 0
    input_price: float = 0.0
    cached_input_price: float = 0.0
    output_price: float = 0.0
    is_provider_smallest: bool = False
    provider: ModelProvider
    model_name: str

    @model_validator(mode="before")
    @classmethod
    def _derive_from_id(cls, data: Any) -> Any:
        if (
            isinstance(data, dict)
            and isinstance(data.get("id"), str)
            and ":" in data["id"]
        ):
            provider, model_name = data["id"].split(":", 1)
            data.setdefault("provider", provider)
            data.setdefault("model_name", model_name)
        return data

    @classmethod
    def entry(cls, **kwargs: Any) -> "ModelEntry":
        """Build an entry from keyword arguments, through the validator."""
        return cls.model_validate(kwargs)


_CLOUD_MODELS: tuple[ModelEntry, ...] = (
    ModelEntry.entry(
        id="openai:gpt-5.6-sol",
        name="GPT-5.6 Sol",
        description="Flagship reasoning - 1.05M context",
        supports_reasoning=True,
        context_size=1_050_000,
        input_price=5.00,
        cached_input_price=0.50,
        output_price=30.00,
    ),
    ModelEntry.entry(
        id="openai:gpt-5.6-terra",
        name="GPT-5.6 Terra",
        description="Balanced 5.6 - 1.05M context",
        supports_reasoning=True,
        context_size=1_050_000,
        input_price=2.00,
        cached_input_price=0.20,
        output_price=12.00,
    ),
    ModelEntry.entry(
        id="openai:gpt-5.6-luna",
        name="GPT-5.6 Luna",
        description="Cheapest OpenAI model - 1.05M context",
        supports_reasoning=True,
        context_size=1_050_000,
        input_price=0.20,
        cached_input_price=0.02,
        output_price=1.20,
        is_provider_smallest=True,
    ),
    ModelEntry.entry(
        id="anthropic:claude-opus-5",
        name="Claude Opus 5",
        description="Deep reasoning and long-horizon agentic work",
        supports_reasoning=True,
        context_size=1_000_000,
        input_price=5.00,
        cached_input_price=0.50,
        output_price=25.00,
    ),
    ModelEntry.entry(
        id="anthropic:claude-sonnet-5",
        name="Claude Sonnet 5",
        description="Near-Opus quality on coding and agentic work",
        supports_reasoning=True,
        context_size=1_000_000,
        input_price=3.00,
        cached_input_price=0.30,
        output_price=15.00,
    ),
    ModelEntry.entry(
        id="anthropic:claude-haiku-4-5",
        name="Claude Haiku 4.5",
        description="Fastest Anthropic model",
        supports_reasoning=True,
        context_size=200_000,
        input_price=1.00,
        cached_input_price=0.10,
        output_price=5.00,
        is_provider_smallest=True,
    ),
    ModelEntry.entry(
        id="google:gemini-3.1-pro-preview",
        name="Gemini 3.1 Pro",
        description="Google flagship - deep reasoning",
        supports_reasoning=True,
        context_size=1_000_000,
        input_price=2.00,
        cached_input_price=0.20,
        output_price=12.00,
    ),
    ModelEntry.entry(
        id="google:gemini-3.6-flash",
        name="Gemini 3.6 Flash",
        description="Latest Flash - fast and capable",
        supports_reasoning=True,
        context_size=1_000_000,
        input_price=1.50,
        cached_input_price=0.15,
        output_price=7.50,
    ),
    ModelEntry.entry(
        id="google:gemini-3.5-flash-lite",
        name="Gemini 3.5 Flash-Lite",
        description="Cheapest Google reasoning model",
        supports_reasoning=True,
        context_size=1_000_000,
        input_price=0.30,
        cached_input_price=0.03,
        output_price=2.50,
        is_provider_smallest=True,
    ),
    ModelEntry.entry(
        id="mock:deterministic",
        name="Mock (deterministic)",
        description="Deterministic mock for E2E testing - no LLM calls",
        context_size=128_000,
        is_provider_smallest=True,
    ),
)


class _OllamaYamlItem(BaseModel):
    """One model entry in the local-model YAML file."""

    model_config = ConfigDict(extra="ignore")

    model: str = ""
    name: str = ""
    thinking: bool = False
    context_size: int = 0


class _OllamaYamlConfig(BaseModel):
    """Top level of the local-model YAML file."""

    model_config = ConfigDict(extra="ignore")

    models: list[_OllamaYamlItem] = []


def _load_ollama_models() -> tuple[ModelEntry, ...]:
    """Load local model entries from the YAML file. Return empty when it is absent."""
    path = _REPO_ROOT / "ollama_models.yaml"
    if not path.is_file():
        return ()

    with path.open() as f:
        data = yaml.safe_load(f)

    if not data:
        return ()

    config = _OllamaYamlConfig.model_validate(data)
    entries: list[ModelEntry] = []
    seen: set[str] = set()
    for item in config.models:
        if not item.model or item.model in seen:
            continue
        display = item.name or item.model
        entries.append(
            ModelEntry.entry(
                id=f"ollama:{item.model}",
                name=f"{display} (local)",
                supports_reasoning=item.thinking,
                context_size=item.context_size,
                is_provider_smallest=not entries,
            )
        )
        seen.add(item.model)

    return tuple(entries)


@lru_cache
def get_model_catalog() -> tuple[ModelEntry, ...]:
    """Return every catalog entry, cloud and local."""
    return _CLOUD_MODELS + _load_ollama_models()


@lru_cache
def _build_index() -> dict[str, ModelEntry]:
    return {m.id: m for m in get_model_catalog()}


def get_model_entry(model_id: str) -> ModelEntry | None:
    """Look up a model by catalog ID. Return None when no entry matches."""
    return _build_index().get(model_id)


def context_window_for(model_id: str) -> int:
    """The model's context window in tokens. An unknown model has no window,
    which reads as 0."""
    entry = _build_index().get(model_id)
    return entry.context_size if entry is not None else 0


def get_smallest_model(provider: ModelProvider) -> ModelEntry:
    """Return the smallest model for a provider.

    Exactly one entry per provider carries the smallest flag.

    :raises LookupError: If the provider has no entry with the flag.
    """
    for entry in get_model_catalog():
        if entry.provider == provider and entry.is_provider_smallest:
            return entry
    msg = f"No is_provider_smallest=True entry for provider={provider!r}"
    raise LookupError(msg)
