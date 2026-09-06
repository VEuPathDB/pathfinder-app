"""attach_wdk_auth context manager — sets+resets veupathdb_auth_token_ctx."""

from __future__ import annotations

import asyncio

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx

from pathfinder.jobs.auth_context import attach_wdk_auth


class TestAttachWdkAuth:
    @pytest.mark.asyncio
    async def test_sets_token_inside_block(self) -> None:
        assert veupathdb_auth_token_ctx.get() is None
        async with attach_wdk_auth("user-cookie"):
            assert veupathdb_auth_token_ctx.get() == "user-cookie"

    @pytest.mark.asyncio
    async def test_resets_on_exit(self) -> None:
        assert veupathdb_auth_token_ctx.get() is None
        async with attach_wdk_auth("user-cookie"):
            pass
        assert veupathdb_auth_token_ctx.get() is None

    @pytest.mark.asyncio
    async def test_resets_even_on_exception(self) -> None:
        class _BoomError(Exception):
            pass

        with pytest.raises(_BoomError):
            async with attach_wdk_auth("user-cookie"):
                raise _BoomError
        assert veupathdb_auth_token_ctx.get() is None

    @pytest.mark.asyncio
    async def test_none_token_clears_ctxvar(self) -> None:
        """If the dispatcher had no cookie, the worker sees None — which
        is what _http.py's fallback chain expects (None → settings)."""
        sentinel = veupathdb_auth_token_ctx.set("pre-existing")
        try:
            async with attach_wdk_auth(None):
                assert veupathdb_auth_token_ctx.get() is None
        finally:
            veupathdb_auth_token_ctx.reset(sentinel)

    @pytest.mark.asyncio
    async def test_concurrent_tasks_do_not_contaminate(self) -> None:
        """asyncio.create_task copies the context at creation — so two
        concurrent turns with different tokens must stay isolated."""
        observed: dict[str, str | None] = {}

        async def run(name: str, token: str) -> None:
            async with attach_wdk_auth(token):
                await asyncio.sleep(0.01)
                observed[name] = veupathdb_auth_token_ctx.get()

        await asyncio.gather(
            run("a", "token-a"),
            run("b", "token-b"),
        )
        assert observed == {"a": "token-a", "b": "token-b"}
