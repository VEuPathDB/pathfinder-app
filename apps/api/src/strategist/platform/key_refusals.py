"""Which provider answers mean the provider refused the key itself.

Each shape is read from a body a provider sent or documents
(``strategist.devtools.provider_refusals``). A status or a body no fixture
shows is not a refusal: the call failed, and the key stays live.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import anthropic
import openai
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

from strategist.domain.provider_keys import KeyableProvider, KeyRefusal

_BAD_REQUEST = 400
_UNAUTHORIZED = 401
_PAYMENT_REQUIRED = 402
_FORBIDDEN = 403
_TOO_MANY_REQUESTS = 429

# OpenAI files every billing refusal under this type and names the cause in code.
_OPENAI_QUOTA = "insufficient_quota"
_OPENAI_BILLING_CODES = frozenset(
    {
        _OPENAI_QUOTA,
        "credit_balance_exhausted",
        "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded",
        "organization_usage_limit_exceeded",
    }
)
# Anthropic answers a low balance as a bad request, told apart by its message.
_ANTHROPIC_LOW_CREDIT = "Your credit balance is too low"
_ANTHROPIC_REJECTED = "invalid_request_error"
_REJECTION_CHARS = 200
_KEY_IN_TEXT = re.compile(r"sk-[A-Za-z0-9_-]+")
_SCHEMA_TOO_LARGE = (
    "The compiled grammar is too large",
    "Schema is too complex for compilation",
)


class _Body(BaseModel):
    """A provider's error body. A body that is not an object carries nothing."""

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _only_an_object_carries_fields(cls, value: Any) -> Any:
        return value if isinstance(value, dict) else {}


class _OpenAIError(_Body):
    """pydantic-ai hands over the ``error`` object of an OpenAI answer."""

    type: str | None = None
    code: str | None = None
    message: str = ""


class _AnthropicDetail(_Body):
    type: str | None = None
    message: str = ""


class _AnthropicError(_Body):
    error: _AnthropicDetail = Field(default_factory=_AnthropicDetail)


class _GoogleReason(_Body):
    reason: str | None = None


class _GoogleDetail(_Body):
    status: str | None = None
    details: list[_GoogleReason] = Field(default_factory=list)


class _GoogleError(_Body):
    error: _GoogleDetail = Field(default_factory=_GoogleDetail)


def _openai(status: int | None, body: object) -> KeyRefusal | None:
    error = _OpenAIError.model_validate(body)
    if status == _UNAUTHORIZED and error.code == "invalid_api_key":
        return KeyRefusal.INVALID
    # A billing error inside a stream carries the body, with or without a status.
    if status in {_TOO_MANY_REQUESTS, None} and (
        error.type == _OPENAI_QUOTA or error.code in _OPENAI_BILLING_CODES
    ):
        return KeyRefusal.NO_CREDIT
    return None


def _anthropic(status: int | None, body: object) -> KeyRefusal | None:
    error = _AnthropicError.model_validate(body).error
    if status == _UNAUTHORIZED and error.type == "authentication_error":
        return KeyRefusal.INVALID
    if status == _PAYMENT_REQUIRED and error.type == "billing_error":
        return KeyRefusal.NO_CREDIT
    if (
        status == _BAD_REQUEST
        and error.type == "invalid_request_error"
        and error.message.startswith(_ANTHROPIC_LOW_CREDIT)
    ):
        return KeyRefusal.NO_CREDIT
    if status == _FORBIDDEN and error.type == "permission_error":
        return KeyRefusal.FORBIDDEN
    return None


def _google(status: int | None, body: object) -> KeyRefusal | None:
    error = _GoogleError.model_validate(body).error
    if status == _BAD_REQUEST and any(
        one.reason == "API_KEY_INVALID" for one in error.details
    ):
        return KeyRefusal.INVALID
    if status == _PAYMENT_REQUIRED:
        return KeyRefusal.NO_CREDIT
    if status == _FORBIDDEN and error.status == "PERMISSION_DENIED":
        return KeyRefusal.FORBIDDEN
    return None


_OPENAI_FLAGGED = "This content was flagged"


def flagged_content(provider: KeyableProvider, failure: ProviderFailure) -> bool:
    if provider != "openai" or failure.status != _BAD_REQUEST:
        return False
    error = _OpenAIError.model_validate(failure.body)
    return error.type == "invalid_request_error" and error.message.startswith(
        _OPENAI_FLAGGED
    )


def classify_refusal(
    provider: KeyableProvider, status: int | None, body: object
) -> KeyRefusal | None:
    """Why the provider refused the key, or None when the answer is no refusal."""
    match provider:
        case "openai":
            return _openai(status, body)
        case "anthropic":
            return _anthropic(status, body)
        case "google":
            return _google(status, body)


# Every error a model request or its stream raises for the provider's answer.
# pydantic-ai wraps an SDK error with the SDK error as its cause; an Anthropic
# response it cannot read passes unwrapped.
PROVIDER_ERRORS: tuple[type[Exception], ...] = (
    ModelAPIError,
    anthropic.APIError,
)


@dataclass(frozen=True)
class ProviderFailure:
    """The status, the body and the headers of one provider error, and the
    type and code the body names, which an operator reads in place of it."""

    status: int | None
    body: object
    headers: dict[str, str] | None = None

    @property
    def kind(self) -> tuple[str | None, str | None]:
        """The provider's error type and code: Anthropic's under its error object,
        OpenAI's at the top of the body."""
        nested = _AnthropicError.model_validate(self.body).error
        if nested.type:
            return nested.type, None
        flat = _OpenAIError.model_validate(self.body)
        return flat.type, flat.code

    @property
    def anthropic_rejection(self) -> str | None:
        """Anthropic's sentence for a request it rejected, with any key masked."""
        error = _AnthropicError.model_validate(self.body).error
        if error.type != _ANTHROPIC_REJECTED or not error.message:
            return None
        return _KEY_IN_TEXT.sub("sk-***", error.message)[:_REJECTION_CHARS]

    @property
    def schema_too_large(self) -> bool:
        """Anthropic would not compile the request's strict schemas."""
        error = _AnthropicError.model_validate(self.body).error
        return error.type == _ANTHROPIC_REJECTED and error.message.startswith(
            _SCHEMA_TOO_LARGE
        )


def provider_failure(error: Exception) -> ProviderFailure:
    """The status and the body ``error`` carries, from any of ``PROVIDER_ERRORS``.

    An SDK error arrives inside a stream the provider accepted, so any status it
    holds is the stream's and not the error's.
    """
    match error:
        case ModelHTTPError():
            return ProviderFailure(error.status_code, error.body, error.headers)
        case ModelAPIError(__cause__=openai.APIError() | anthropic.APIError() as cause):
            return ProviderFailure(None, cause.body)
        case anthropic.APIError():
            return ProviderFailure(None, error.body)
        case _:
            return ProviderFailure(None, None)
