"""The catalog of selectable LLM models, the one module that names a model id."""

from collections import Counter
from datetime import date
from functools import lru_cache
from typing import Any, Final, Literal

import yaml
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import ModelProvider
from pydantic import BaseModel, ConfigDict, model_validator

from pathfinder.domain.provider_keys import KEYABLE_PROVIDERS
from pathfinder.platform.paths import REPO_ROOT

__all__ = [
    "DEFAULT_MODEL_ID",
    "PRICES_AS_OF",
    "ModelEntry",
    "ModelRank",
    "context_window_for",
    "get_model_catalog",
    "get_model_entry",
    "get_smallest_model",
    "provider_default",
    "validate_lineup",
]

# The place a model holds in its provider's lineup; the tiers are derived from it.
type ModelRank = Literal["flagship", "standard", "small"]


class ModelEntry(CamelModel):
    """One model in the catalog.

    The ID holds the provider and the model name, joined by a colon.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    description: str = ""
    supports_reasoning: bool = False
    # Each flag is a measurement: the provider was sent one PNG and one PDF.
    supports_images: bool = False
    supports_documents: bool = False
    context_size: int = 0
    input_price: float = 0.0
    cached_input_price: float = 0.0
    output_price: float = 0.0
    rank: ModelRank
    is_provider_default: bool = False
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


def validate_lineup(entries: tuple[ModelEntry, ...]) -> tuple[ModelEntry, ...]:
    """Return ``entries`` when each cloud provider in them holds one default
    entry, one small entry and at most one entry per rank.

    :raises ValueError: If a provider breaks one of these rules.
    """
    for provider in KEYABLE_PROVIDERS:
        held = [e for e in entries if e.provider == provider]
        if not held:
            continue
        defaults = sum(e.is_provider_default for e in held)
        ranks = Counter(e.rank for e in held)
        twice = [rank for rank, n in ranks.items() if n > 1]
        if defaults != 1 or ranks["small"] != 1 or twice:
            msg = (
                f"{provider!r} lineup holds {defaults} default and "
                f"{ranks['small']} small entries"
                + "".join(f", rank {rank!r} twice" for rank in twice)
            )
            raise ValueError(msg)
    return entries


_CLOUD_MODELS: tuple[ModelEntry, ...] = validate_lineup(
    (
        ModelEntry.entry(
            id="openai:gpt-6-sol",
            name="GPT-6 Sol",
            description="OpenAI flagship reasoning - 1.05M context",
            rank="flagship",
            supports_reasoning=True,
            supports_images=True,
            supports_documents=True,
            context_size=1_050_000,
            input_price=2.00,
            cached_input_price=0.20,
            output_price=10.00,
        ),
        ModelEntry.entry(
            id="openai:gpt-6-luna",
            name="GPT-6 Luna",
            description="Cheapest OpenAI model - 1.05M context",
            rank="small",
            supports_reasoning=True,
            supports_images=True,
            supports_documents=True,
            context_size=1_050_000,
            input_price=0.10,
            cached_input_price=0.01,
            output_price=0.50,
        ),
        ModelEntry.entry(
            id="openai:gpt-5.6-luna",
            name="GPT-5.6 Luna",
            description="Proven GPT-5.6 - 1.05M context",
            rank="standard",
            is_provider_default=True,
            supports_reasoning=True,
            supports_images=True,
            supports_documents=True,
            context_size=1_050_000,
            input_price=0.20,
            cached_input_price=0.02,
            output_price=1.20,
        ),
        ModelEntry.entry(
            id="anthropic:claude-haiku-4-5",
            name="Claude Haiku 4.5",
            description="Fastest Anthropic model",
            rank="small",
            is_provider_default=True,
            supports_reasoning=True,
            context_size=200_000,
            input_price=1.00,
            cached_input_price=0.10,
            output_price=5.00,
        ),
        ModelEntry.entry(
            id="google:gemini-3.1-pro-preview",
            name="Gemini 3.1 Pro",
            description="Google flagship - deep reasoning",
            rank="flagship",
            supports_reasoning=True,
            supports_images=True,
            supports_documents=True,
            context_size=1_000_000,
            input_price=2.00,
            cached_input_price=0.20,
            output_price=12.00,
        ),
        ModelEntry.entry(
            id="google:gemini-3.8-flash",
            name="Gemini 3.8 Flash",
            description="Latest Flash - fast and capable",
            rank="standard",
            is_provider_default=True,
            supports_reasoning=True,
            supports_images=True,
            supports_documents=True,
            context_size=1_048_576,
            input_price=0.75,
            cached_input_price=0.075,
            output_price=3.75,
        ),
        ModelEntry.entry(
            id="google:gemini-3.5-flash-lite",
            name="Gemini 3.5 Flash-Lite",
            description="Cheapest Google reasoning model",
            rank="small",
            supports_reasoning=True,
            supports_images=True,
            supports_documents=True,
            context_size=1_000_000,
            input_price=0.30,
            cached_input_price=0.03,
            output_price=2.50,
        ),
        ModelEntry.entry(
            id="mock:deterministic",
            name="Mock (deterministic)",
            description="Deterministic mock for E2E testing - no LLM calls",
            rank="small",
            context_size=128_000,
        ),
    )
)

# The day the prices above were last checked against each provider's page.
PRICES_AS_OF: Final = date(2026, 9, 28)


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
    path = REPO_ROOT / "ollama_models.yaml"
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
                rank="standard" if entries else "small",
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
    """Return the provider's one ``small`` entry.

    :raises LookupError: If the provider has no ``small`` entry.
    """
    for entry in get_model_catalog():
        if entry.provider == provider and entry.rank == "small":
            return entry
    msg = f"No small entry for provider={provider!r}"
    raise LookupError(msg)


def provider_default(
    provider: ModelProvider, entries: tuple[ModelEntry, ...] = _CLOUD_MODELS
) -> ModelEntry:
    """Return the entry a provider runs when nothing else is picked.

    :raises LookupError: If no entry of the provider is marked default.
    """
    for entry in entries:
        if entry.provider == provider and entry.is_provider_default:
            return entry
    msg = f"No default entry for provider={provider!r}"
    raise LookupError(msg)


# Every role runs on this model when no tier and no pick names another.
DEFAULT_MODEL_ID: Final = provider_default("openai").id
