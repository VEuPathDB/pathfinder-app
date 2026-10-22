from __future__ import annotations

from pydantic_ai import RunContext

REFUSALS_PER_CHECK = 2


def may_refuse[DepsT](ctx: RunContext[DepsT], used: int) -> bool:
    return used < REFUSALS_PER_CHECK and ctx.retry < ctx.max_retries
