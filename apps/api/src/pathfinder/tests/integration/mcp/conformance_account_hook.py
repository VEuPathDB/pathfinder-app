"""The account-state extension point, answered for a VEuPathDB account.

The conformance suite asks what the credential's account holds so that it can
compare it across a read-only call. For WDK that is the account's strategies,
which every write in the served inventory creates and every read leaves alone.
The suite loads this module with ``-p`` and never imports it.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Sequence

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.wdk.factory import get_strategy_api

from pathfinder.tests.integration.mcp._served import SITE

BEARER_VARIABLE = "MCP_CONFORMANCE_BEARER"

AccountSnapshot = Callable[[], Awaitable[Sequence[str]]]


async def strategy_identifiers() -> Sequence[str]:
    """Every strategy the credential's account holds, in a stable order."""
    reset = veupathdb_auth_token_ctx.set(os.environ[BEARER_VARIABLE])
    try:
        summaries = await get_strategy_api(SITE).list_strategies()
    finally:
        veupathdb_auth_token_ctx.reset(reset)
    return sorted(str(summary.strategy_id) for summary in summaries)


def pytest_mcp_account_state() -> AccountSnapshot:
    return strategy_identifiers
