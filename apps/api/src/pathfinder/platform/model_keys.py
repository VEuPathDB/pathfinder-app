"""The model a call runs on, under the key that pays for it.

A researcher's live key pays for its provider; the deployment pays for the
rest. Every resolved model is guarded, so a provider's error body reaches no
chunk, log or trace, and a key the provider refuses is recorded for the turn.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from assistant_core.platform.types import ModelProvider, PaidBy
from pydantic import SecretStr
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse
from pydantic_ai.models import (
    Model,
    ModelRequestParameters,
    StreamedResponse,
    infer_model,
)
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.providers import Provider, infer_provider
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from pathfinder.domain.provider_keys import (
    KEYABLE_PROVIDERS,
    PROVIDER_NAMES,
    KeyableProvider,
    KeyRefusal,
    NobodyPays,
    ProviderKeyring,
    RefusedKey,
    provider_name,
    provider_of,
)
from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import (
    ProviderKeyRefusedError,
    ProviderNotConfiguredError,
    ProviderUnreachableError,
    refused_key_error,
)
from pathfinder.platform.key_refusals import classify_refusal

type ProviderBuilder = Callable[[KeyableProvider, SecretStr], Provider[Any]]
type KeyProbe = Callable[[KeyableProvider, str, SecretStr], Awaitable[None]]

_PROBE_TOKENS = 16
# A provider that asks the caller to wait did not judge the key.
_WAIT_STATUSES = frozenset({408, 429})
_SERVER_ERROR = 500


def build_provider(name: KeyableProvider, key: SecretStr) -> Provider[Any]:
    """The provider client that sends ``key``, and no key from the environment."""
    secret = key.get_secret_value()
    match name:
        case "openai":
            return OpenAIProvider(api_key=secret)
        case "anthropic":
            return AnthropicProvider(api_key=secret)
        case "google":
            return GoogleProvider(api_key=secret)


@dataclass
class TurnKeys:
    """The keys one turn runs under, and the refusals it met on the way."""

    keyring: ProviderKeyring
    build: ProviderBuilder = build_provider
    refusals: dict[KeyableProvider, KeyRefusal] = field(default_factory=dict)


_turn_keys: ContextVar[TurnKeys | None] = ContextVar("turn_keys", default=None)


@contextmanager
def attach_keyring(
    keyring: ProviderKeyring, build: ProviderBuilder = build_provider
) -> Iterator[TurnKeys]:
    """Run a turn under ``keyring``. The keys live in this scope and nowhere else."""
    keys = TurnKeys(keyring=keyring, build=build)
    token = _turn_keys.set(keys)
    try:
        yield keys
    finally:
        _turn_keys.reset(token)


def _current() -> TurnKeys:
    return _turn_keys.get() or TurnKeys(keyring=ProviderKeyring())


def turn_refusals() -> dict[KeyableProvider, KeyRefusal]:
    """The keys a provider refused during this turn."""
    return dict(_current().refusals)


def turn_paid_by(model_id: str) -> PaidBy:
    """Who pays for a call to ``model_id`` in this turn."""
    active = _current().keyring.active
    return PaidBy.USER if model_id.partition(":")[0] in active else PaidBy.DEPLOYMENT


class GuardedModel(WrapperModel):
    """A model whose provider errors carry the status and never the body.

    A refusal of the researcher's key is recorded for the turn and raised as
    the typed refusal.
    """

    _keys: TurnKeys
    _keyed: KeyableProvider | None

    def __init__(
        self, wrapped: Model, *, keys: TurnKeys, keyed: KeyableProvider | None
    ) -> None:
        super().__init__(wrapped)
        self._keys = keys
        self._keyed = keyed

    def _failure(self, error: ModelHTTPError) -> Exception:
        if self._keyed is not None:
            refusal = classify_refusal(self._keyed, error.status_code, error.body)
            if refusal is not None:
                self._keys.refusals[self._keyed] = refusal
                return ProviderKeyRefusedError(PROVIDER_NAMES[self._keyed], refusal)
        return ModelHTTPError(
            error.status_code, error.model_name, headers=error.headers
        )

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        try:
            response = await super().request(
                messages, model_settings, model_request_parameters
            )
        except ModelHTTPError as error:
            failure = self._failure(error)
        else:
            return response
        # Raised outside the handler, so the provider's error is not its context.
        raise failure

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[Any] | None = None,
    ) -> AsyncIterator[StreamedResponse]:
        try:
            async with super().request_stream(
                messages, model_settings, model_request_parameters, run_context
            ) as response:
                yield response
        except ModelHTTPError as error:
            failure = self._failure(error)
        else:
            return
        raise failure


def _deployment_provider(name: str, keys: TurnKeys) -> Provider[Any]:
    """The deployment's own provider, sending the key its settings hold.

    A provider the deployment holds no key for is refused when it is built.
    """
    settings = get_settings()
    for keyable in KEYABLE_PROVIDERS:
        if keyable == name:
            credential = settings.deployment_credential(keyable)
            if not credential.strip():
                raise ProviderNotConfiguredError(provider_name(keyable))
            return keys.build(keyable, SecretStr(credential))
    return infer_provider(name)


def _users_key(
    provider: ModelProvider, keys: TurnKeys
) -> tuple[KeyableProvider, SecretStr] | None:
    """The researcher's key that pays for ``provider``, or None for the deployment.

    A key refused before or during this turn raises; nothing falls back.
    """
    for refused, refusal in keys.refusals.items():
        if refused == provider:
            raise ProviderKeyRefusedError(provider_name(provider), refusal)
    deployment = get_settings().deployment_providers
    match keys.keyring.statuses().payer(provider, deployment):
        case RefusedKey(refusal=refusal):
            raise refused_key_error(provider_name(provider), refusal)
        case NobodyPays():
            raise ProviderNotConfiguredError(provider_name(provider))
        case _:
            return keys.keyring.keyed(provider)


def keyed_model(model: Model | str) -> Model | str:
    """The model ``model`` names, on the key that pays for it this turn.

    A model already built, and every model of a mock deployment, pass unchanged.
    """
    if isinstance(model, Model) or _is_mock_deployment():
        return model
    keys = _current()
    users_key = _users_key(provider_of(model), keys)
    if users_key is None:
        return deployment_model(model, keys)
    keyed, key = users_key
    built = infer_model(model, provider_factory=lambda _: keys.build(keyed, key))
    return GuardedModel(built, keys=keys, keyed=keyed)


def deployment_model(model_id: str, keys: TurnKeys | None = None) -> Model:
    """``model_id`` on the deployment's key, whatever keys the turn holds."""
    scope = keys or TurnKeys(keyring=ProviderKeyring(), build=_current().build)
    built = infer_model(
        model_id, provider_factory=lambda name: _deployment_provider(name, scope)
    )
    return GuardedModel(built, keys=scope, keyed=None)


def _is_mock_deployment() -> bool:
    return get_settings().pathfinder_chat_provider.strip().lower() == "mock"


async def one_generation(model: Model) -> None:
    """One short generation request, which proves authentication and billing."""
    async with model:
        await model.request(
            [ModelRequest.user_text_prompt("ok")],
            {"max_tokens": _PROBE_TOKENS},
            ModelRequestParameters(),
        )


def _probe_failure(provider: KeyableProvider, error: ModelHTTPError) -> Exception:
    """A refusal refuses the key; a wait or an outage judged nothing."""
    name = PROVIDER_NAMES[provider]
    refusal = classify_refusal(provider, error.status_code, error.body)
    if refusal is not None:
        return ProviderKeyRefusedError(name, refusal, status=422)
    if error.status_code in _WAIT_STATUSES or error.status_code >= _SERVER_ERROR:
        return ProviderUnreachableError(name)
    return ProviderKeyRefusedError(name, status=422)


async def probe_key(
    provider: KeyableProvider,
    model_id: str,
    key: SecretStr,
    build: ProviderBuilder = build_provider,
) -> None:
    """Refuse a key the provider does not accept, before anything stores it.

    ``model_id`` is the provider's cheapest model; one short generation proves
    both the key and its credit.
    """
    model = infer_model(model_id, provider_factory=lambda _: build(provider, key))
    name = PROVIDER_NAMES[provider]
    try:
        await one_generation(model)
    except ModelHTTPError as error:
        failure: Exception = _probe_failure(provider, error)
    except ModelAPIError:
        failure = ProviderUnreachableError(name)
    else:
        return
    raise failure
