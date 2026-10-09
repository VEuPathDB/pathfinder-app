"""The VEuPathDB credential a durable call carries to the worker that answers it.

A worker inherits no context variable from the process that deferred the job,
so the token is captured at the call and restored around the body. It is a
``CarriedSecret``, so it masks itself wherever the state is printed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from assistant_core.tasks.job_context import CarriedSecret, DurableJobState
from pydantic import SecretStr
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.wdk import search_turn

from pathfinder.jobs.auth_context import attach_wdk_auth


class WdkJobState(DurableJobState):
    """What a durable call carries: the caller's WDK session token."""

    veupathdb_auth_token: CarriedSecret | None = None


class WdkJobContext:
    """Capture the WDK token at the call, restore it around the body."""

    state_type = WdkJobState

    def capture(self) -> WdkJobState:
        token = veupathdb_auth_token_ctx.get()
        return WdkJobState(
            veupathdb_auth_token=None if token is None else SecretStr(token),
        )

    def restore(self, state: DurableJobState) -> AbstractAsyncContextManager[None]:
        carried = WdkJobState.model_validate(state.model_dump())
        secret = carried.veupathdb_auth_token
        return _restored(None if secret is None else secret.get_secret_value())


@asynccontextmanager
async def _restored(token: str | None) -> AsyncIterator[None]:
    async with attach_wdk_auth(token):
        with search_turn():
            yield


__all__ = ["WdkJobContext", "WdkJobState"]
