"""Which provider answers mean the provider refused the key itself.

Each shape is read from a body the provider sent a made-up key
(``pathfinder.devtools.provider_refusals``). A status or a body no recording
shows is not a refusal: the call failed, and the key stays live.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pathfinder.domain.provider_keys import KeyableProvider, KeyRefusal

_UNAUTHORIZED = 401
_BAD_REQUEST = 400


class _Body(BaseModel):
    """A provider's error body. A body that is not an object carries nothing."""

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _only_an_object_carries_fields(cls, value: Any) -> Any:
        return value if isinstance(value, dict) else {}


class _OpenAIError(_Body):
    """pydantic-ai hands over the ``error`` object of an OpenAI answer."""

    code: str | None = None


class _AnthropicDetail(_Body):
    type: str | None = None


class _AnthropicError(_Body):
    error: _AnthropicDetail = Field(default_factory=_AnthropicDetail)


class _GoogleReason(_Body):
    reason: str | None = None


class _GoogleDetail(_Body):
    details: list[_GoogleReason] = Field(default_factory=list)


class _GoogleError(_Body):
    error: _GoogleDetail = Field(default_factory=_GoogleDetail)


def classify_refusal(
    provider: KeyableProvider, status: int, body: object
) -> KeyRefusal | None:
    """``INVALID`` when the answer says the provider does not accept the key."""
    refused = False
    match provider:
        case "openai":
            refused = (
                status == _UNAUTHORIZED
                and _OpenAIError.model_validate(body).code == "invalid_api_key"
            )
        case "anthropic":
            refused = (
                status == _UNAUTHORIZED
                and _AnthropicError.model_validate(body).error.type
                == "authentication_error"
            )
        case "google":
            reasons = _GoogleError.model_validate(body).error.details
            refused = status == _BAD_REQUEST and any(
                one.reason == "API_KEY_INVALID" for one in reasons
            )
    return KeyRefusal.INVALID if refused else None
