"""The turn context a durable job's body runs under."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from assistant_core.platform.db import async_session_factory

from pathfinder.ai.graph.runtime import Context
from pathfinder.domain.strategy.session import StrategySession


def job_context(*, site_id: str = "plasmodb", user_id: UUID | None = None) -> Context:
    """The context a job impl reads its site and its database from."""
    return Context(
        site_id=site_id,
        user_id=user_id or uuid4(),
        strategy_session=StrategySession(site_id=site_id),
        db_session_factory=async_session_factory,
        cancel_event=asyncio.Event(),
    )
