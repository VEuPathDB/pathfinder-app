"""The request-scoped ContextVars a job body runs under.

A worker inherits no ``ContextVar`` state from the process that deferred the
job, so these helpers set the values for the block and reset them on exit.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from assistant_core.platform.context import application_id_ctx, user_id_ctx
from veupathdb.auth_context import veupathdb_auth_token_ctx

from pathfinder.platform.identity import PATHFINDER_APPLICATION_ID
from pathfinder.services.conversations.authz import conversation_application_id


@asynccontextmanager
async def attach_application() -> AsyncIterator[None]:
    """Run the block as this application, where no request or thread names one.

    A periodic job and the chat debugger both write application-scoped rows
    with nothing upstream to read an application from.
    """
    reset = application_id_ctx.set(PATHFINDER_APPLICATION_ID)
    try:
        yield
    finally:
        application_id_ctx.reset(reset)


@asynccontextmanager
async def attach_wdk_auth(token: str | None) -> AsyncIterator[None]:
    """Set ``veupathdb_auth_token_ctx`` to ``token`` inside the block."""
    reset = veupathdb_auth_token_ctx.set(token)
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(reset)


@asynccontextmanager
async def attach_user_id(user_id: UUID | None) -> AsyncIterator[None]:
    """Set ``user_id_ctx`` to ``user_id`` inside the block."""
    reset = user_id_ctx.set(user_id)
    try:
        yield
    finally:
        user_id_ctx.reset(reset)


@asynccontextmanager
async def attach_conversation_application(
    conversation_id: UUID,
) -> AsyncIterator[None]:
    """Run the block as the application that holds ``conversation_id``.

    The conversation row is the only record of which application a turn
    belongs to, so a job that cannot read it must not run.
    """
    application_id = await conversation_application_id(conversation_id)
    if application_id is None:
        msg = f"conversation {conversation_id} not found"
        raise LookupError(msg)
    reset = application_id_ctx.set(application_id)
    try:
        yield
    finally:
        application_id_ctx.reset(reset)


__all__ = [
    "attach_application",
    "attach_conversation_application",
    "attach_user_id",
    "attach_wdk_auth",
]
