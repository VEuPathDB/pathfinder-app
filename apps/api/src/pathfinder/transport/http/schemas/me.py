from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import ModelProvider, PaidBy
from pydantic import Field, SecretStr

from pathfinder.domain.provider_keys import KeyableProvider
from pathfinder.services.provider_keys import ProviderKeyView


class QuotaResponse(CamelModel):
    """The allowance the deployment pays for, and the spend on the user's keys.

    ``used_usd``, ``total_tokens`` and ``percent`` count deployment-paid spend
    only, so the limit caps what it says it caps.
    """

    used_usd: Decimal
    limit_usd: Decimal
    total_tokens: int
    percent: float
    resets_at: datetime
    own_key_usd: Decimal
    own_key_tokens: int
    own_key_providers: list[KeyableProvider]


class ProviderKeyIn(CamelModel):
    """A provider key as the researcher enters it. It is never sent back."""

    key: SecretStr = Field(min_length=20, max_length=512)


class ProviderKeysResponse(CamelModel):
    """The researcher's stored keys, and who pays for each provider now."""

    enabled: bool
    keys: list[ProviderKeyView]
    payers: dict[ModelProvider, PaidBy]
