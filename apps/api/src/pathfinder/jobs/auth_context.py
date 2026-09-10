"""The two context variables this product owns, for a job body that runs here.

The application id and the WDK token are this deployment's; the user and the
thread's application are the runtime's (``assistant_core.tasks.scope``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from assistant_core.platform.context import application_id_ctx
from veupathdb.auth_context import veupathdb_auth_token_ctx

from pathfinder.platform.identity import PATHFINDER_APPLICATION_ID


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


__all__ = ["attach_application", "attach_wdk_auth"]
