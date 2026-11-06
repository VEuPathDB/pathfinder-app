"""The shape of one catalog entry, its prices, and the rules a provider's lineup keeps."""

from collections import Counter
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Literal

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import ModelProvider
from assistant_core.pricing import HostModelPrice, LongPrompt, TokenPrices
from pydantic import ConfigDict, model_validator

from pathfinder.domain.provider_keys import KEYABLE_PROVIDERS

__all__ = [
    "CatalogMeter",
    "LongPromptPrices",
    "ModelEntry",
    "ModelRank",
    "TierRank",
    "require_catalogued",
    "validate_lineup",
]

# The place a model holds in its provider's lineup; the tiers are derived from it.
# An unranked model holds no place and runs only when a role picks it.
type TierRank = Literal["flagship", "standard", "small"]
type ModelRank = Literal[TierRank, "unranked"]


def _mtok(price: float) -> Decimal:
    return Decimal(str(price))


class LongPromptPrices(CamelModel):
    model_config = ConfigDict(frozen=True)

    above_tokens: int
    input_price: float
    cached_input_price: float
    cache_write_price: float
    output_price: float

    def token_prices(self) -> TokenPrices:
        return TokenPrices(
            input_mtok=_mtok(self.input_price),
            cache_read_mtok=_mtok(self.cached_input_price),
            cache_write_mtok=_mtok(self.cache_write_price),
            output_mtok=_mtok(self.output_price),
        )


class CatalogMeter(CamelModel):
    model_config = ConfigDict(frozen=True)

    cache_write_price: float
    long_prompt: LongPromptPrices | None = None


class ModelEntry(CamelModel):
    """One model in the catalog.

    The ID holds the provider and the model name, joined by a colon.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    description: str = ""
    supports_reasoning: bool = False
    # Each flag is a measurement (one PNG and one PDF), or the provider's
    # documented support for a model not yet measured.
    supports_images: bool = False
    supports_documents: bool = False
    context_size: int = 0
    input_price: float = 0.0
    cached_input_price: float = 0.0
    output_price: float = 0.0
    rank: ModelRank
    is_provider_default: bool = False
    deployment_may_pay: bool = False
    meter: CatalogMeter | None = None
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

    @model_validator(mode="after")
    def _unranked_is_not_a_default(self) -> "ModelEntry":
        if self.rank == "unranked" and self.is_provider_default:
            msg = f"{self.id}: an unranked entry is never its provider's default"
            raise ValueError(msg)
        return self

    @classmethod
    def entry(cls, **kwargs: Any) -> "ModelEntry":
        """Build an entry from keyword arguments, through the validator."""
        return cls.model_validate(kwargs)

    def host_price(self) -> HostModelPrice | None:
        if self.meter is None:
            return None
        long = self.meter.long_prompt
        return HostModelPrice(
            provider=self.provider,
            model=self.model_name,
            prices=TokenPrices(
                input_mtok=_mtok(self.input_price),
                cache_read_mtok=_mtok(self.cached_input_price),
                cache_write_mtok=_mtok(self.meter.cache_write_price),
                output_mtok=_mtok(self.output_price),
            ),
            long_prompt=None
            if long is None
            else LongPrompt(above_tokens=long.above_tokens, prices=long.token_prices()),
        )


def _lineup_fault(held: list[ModelEntry]) -> str | None:
    defaults = sum(e.is_provider_default for e in held)
    ranks = Counter(e.rank for e in held if e.rank != "unranked")
    twice = [rank for rank, n in ranks.items() if n > 1]
    if defaults == 1 and ranks["small"] == 1 and not twice:
        return None
    return f"{defaults} default and {ranks['small']} small entries" + "".join(
        f", rank {rank!r} twice" for rank in twice
    )


def validate_lineup(entries: tuple[ModelEntry, ...]) -> tuple[ModelEntry, ...]:
    """Return ``entries`` when each cloud provider in them holds one default
    entry, one small entry and at most one entry per tier rank, both in its
    whole lineup and in the part of it the deployment pays for.

    :raises ValueError: If a provider breaks one of these rules.
    """
    for provider in KEYABLE_PROVIDERS:
        held = [e for e in entries if e.provider == provider]
        if not held:
            continue
        fault = _lineup_fault(held)
        if fault is not None:
            msg = f"{provider!r} lineup holds {fault}"
            raise ValueError(msg)
        fault = _lineup_fault([e for e in held if e.deployment_may_pay])
        if fault is not None:
            msg = f"{provider!r}: the deployment pays for {fault}"
            raise ValueError(msg)
    return entries


def require_catalogued[K: str](
    models: Mapping[K, str], entries: tuple[ModelEntry, ...]
) -> Mapping[K, str]:
    ids = {e.id for e in entries}
    missing = sorted(set(models.values()) - ids)
    if missing:
        msg = f"models the catalog lacks: {missing}"
        raise ValueError(msg)
    return models
