"""What a durable call carries from its turn to the worker that answers it: the
caller's VEuPathDB credential and the model a debugger or eval run pins.

A worker inherits no context variable from the process that deferred the job,
so both are captured at the call and restored around the body. The token is a
``CarriedSecret``, so it masks itself wherever the state is printed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from assistant_core.tasks.job_context import CarriedSecret, DurableJobState
from pydantic import SecretStr
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.wdk import search_turn

from strategist.jobs.auth_context import attach_wdk_auth
from strategist.platform.pinned_model import pin_model, pinned_model


class TurnJobState(DurableJobState):
    """What a durable call carries: the caller's WDK session token and the run's pin."""

    veupathdb_auth_token: CarriedSecret | None = None
    pinned_model: str | None = None


class TurnJobContext:
    """Capture the WDK token and the pin at the call, restore both around the body."""

    state_type = TurnJobState

    def capture(self) -> TurnJobState:
        token = veupathdb_auth_token_ctx.get()
        return TurnJobState(
            veupathdb_auth_token=None if token is None else SecretStr(token),
            pinned_model=pinned_model(),
        )

    def restore(self, state: DurableJobState) -> AbstractAsyncContextManager[None]:
        carried = TurnJobState.model_validate(state.model_dump())
        secret = carried.veupathdb_auth_token
        return _restored(
            None if secret is None else secret.get_secret_value(),
            carried.pinned_model,
        )


@asynccontextmanager
async def _restored(token: str | None, model_id: str | None) -> AsyncIterator[None]:
    async with attach_wdk_auth(token):
        with pin_model(model_id), search_turn():
            yield


__all__ = ["TurnJobContext", "TurnJobState"]
