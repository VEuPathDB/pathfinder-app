from __future__ import annotations

from dataclasses import dataclass

from pathfinder.platform.config import Settings

__all__ = [
    "CONNECTION_BUDGET",
    "DATABASE_CONNECTION_LIMIT",
    "OPENER_CALLS",
    "PROCRASTINATE_WORKERS",
    "PoolBudget",
    "connection_budget",
]

DATABASE_CONNECTION_LIMIT = 100
CONNECTION_BUDGET = 90
PROCRASTINATE_WORKERS = 2
OPENER_CALLS = {
    "assistant_core.conversation.checkpointer": 1,
    "assistant_core.conversation.listen_hub": 1,
    "assistant_core.memory.lifespan": 1,
    "assistant_core.platform.db": 1,
    "assistant_core.tasks.heartbeat": 1,
    "pathfinder.jobs.app": 1,
    "pathfinder.services.audit.lease_pool": 1,
    "pathfinder.services.conversations.thread_lock": 1,
    "veupathdb_mcp.embeddings.db": 1,
    "veupathdb_mcp.search_line.line": 1,
    "veupathdb_mcp.strategy_line.line": 1,
}


@dataclass(frozen=True)
class PoolBudget:
    process: str
    source: str
    opened_by: tuple[str, ...]
    worst_case: int


def connection_budget(settings: Settings) -> tuple[PoolBudget, ...]:
    request = settings.db_pool_size + settings.db_max_overflow
    line = settings.search_line_pool_size + settings.search_line_max_overflow
    strategy_line = (
        settings.strategy_line_pool_size + settings.strategy_line_max_overflow
    )
    embedding = settings.embedding_db_pool_size + settings.embedding_db_max_overflow
    return (
        PoolBudget("api", "request pool", ("assistant_core.platform.db",), request),
        PoolBudget(
            "api",
            "thread lock pool",
            ("pathfinder.services.conversations.thread_lock",),
            settings.lock_pool_size + settings.lock_pool_overflow,
        ),
        PoolBudget(
            "api",
            "job queue pool",
            ("pathfinder.jobs.app",),
            settings.job_queue_pool_max_size,
        ),
        PoolBudget(
            "api",
            "graph checkpointer",
            ("assistant_core.conversation.checkpointer",),
            1,
        ),
        PoolBudget("api", "memory store", ("assistant_core.memory.lifespan",), 1),
        PoolBudget(
            "api",
            "shared LISTEN connection of the chat streams",
            ("assistant_core.conversation.listen_hub",),
            1,
        ),
        PoolBudget(
            "api",
            "expensive-search line",
            ("veupathdb_mcp.search_line.line",),
            line,
        ),
        PoolBudget(
            "api",
            "strategy line",
            ("veupathdb_mcp.strategy_line.line",),
            strategy_line,
        ),
        PoolBudget("worker", "request pool", ("assistant_core.platform.db",), request),
        PoolBudget(
            "worker",
            "job queue pool",
            ("pathfinder.jobs.app",),
            settings.job_queue_pool_max_size,
        ),
        PoolBudget(
            "worker",
            "job queue LISTEN, one per procrastinate worker",
            ("procrastinate.psycopg_connector",),
            PROCRASTINATE_WORKERS,
        ),
        PoolBudget(
            "worker",
            "checkpointer and memory store of each running job",
            (
                "assistant_core.conversation.checkpointer",
                "assistant_core.memory.lifespan",
            ),
            2 * settings.worker_concurrency,
        ),
        PoolBudget(
            "worker",
            "audit run and review leases, one per audit job",
            ("pathfinder.services.audit.lease_pool",),
            settings.audit_concurrency,
        ),
        PoolBudget(
            "worker",
            "heartbeat, one per procrastinate worker",
            ("assistant_core.tasks.heartbeat",),
            PROCRASTINATE_WORKERS,
        ),
        PoolBudget(
            "worker",
            "expensive-search line",
            ("veupathdb_mcp.search_line.line",),
            line,
        ),
        PoolBudget(
            "worker",
            "strategy line",
            ("veupathdb_mcp.strategy_line.line",),
            strategy_line,
        ),
        PoolBudget(
            "wdk-mcp",
            "embedding index pool",
            ("veupathdb_mcp.embeddings.db",),
            embedding,
        ),
        PoolBudget(
            "wdk-mcp",
            "expensive-search line",
            ("veupathdb_mcp.search_line.line",),
            line,
        ),
        PoolBudget(
            "wdk-mcp",
            "strategy line",
            ("veupathdb_mcp.strategy_line.line",),
            strategy_line,
        ),
    )
