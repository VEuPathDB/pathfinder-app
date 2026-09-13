"""LLM-callable memory tools: search_memory + remember."""

from __future__ import annotations

from datetime import UTC, datetime

from assistant_core.graph.tool_summary import with_summary
from assistant_core.memory.retrieval import rerank_by_hybrid_score
from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import MemoryStore, StoredMemory
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ToolReturn
from pydantic_ai.tools import RunContext

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.domain.memory import (
    MEMORY_KINDS,
    STANDING_MEMORY_KINDS,
    MemoryKind,
    UnnamedMemoryError,
    standing_memory_key,
)


def _standing_key(kind: MemoryKind, name: str) -> str | None:
    """The key a kind of this name is written under, or None for a new row."""
    if kind not in STANDING_MEMORY_KINDS:
        return None
    try:
        return standing_memory_key(name)
    except UnnamedMemoryError as unnamed:
        msg = (
            f"{unnamed} Call remember again with a short name for what this "
            f"states, such as 'Default organism'."
        )
        raise ModelRetry(msg) from unnamed


async def search_memory(
    ctx: RunContext[AgentDeps],
    query: str,
    kind: MemoryKind | None = None,
    top_k: int = 5,
) -> ToolReturn[list[dict[str, object]]]:
    """Search the user's cross-thread memory semantically.

    Use this when the user references prior work, asks "what did we do before",
    or when recalling past context would improve your answer.

    Distributes ``top_k`` across every namespace (or uses the full budget if
    ``kind`` is given), then reranks globally via the hybrid score so the most
    relevant hits across namespaces come first. ``kind="case"`` returns the
    goals past runs verified, with the searches, params and counts that landed.
    """
    store_raw = ctx.deps.memory_store
    user_id = ctx.deps.user_id
    if store_raw is None or user_id is None:
        return with_summary(
            [],
            f"0 memories for {query}",
            ctx=ctx,
            status="empty",
        )
    mem_store = MemoryStore(store=store_raw)
    kinds: tuple[str, ...] = (kind,) if kind is not None else MEMORY_KINDS
    per_kind = max(1, top_k) if len(kinds) == 1 else max(1, top_k // len(kinds))

    all_hits: list[StoredMemory] = []
    for k in kinds:
        hits = await mem_store.semantic_search(
            user_id=user_id,
            kind=k,
            query=query,
            top_k=per_kind,
        )
        all_hits.extend(hits)
    reranked = rerank_by_hybrid_score(all_hits)
    found = [stored.value.model_dump(mode="json") for stored in reranked[:top_k]]
    return with_summary(
        found,
        f"{len(found)} memories for {query}",
        ctx=ctx,
        status="ok" if found else "empty",
    )


async def remember(
    ctx: RunContext[AgentDeps],
    kind: MemoryKind,
    name: str,
    summary: str,
    content: dict[str, object],
    tags: list[str] | None = None,
) -> ToolReturn[str]:
    """Store an explicit memory for this user.

    Use for biological facts the user has taught you or preferences they've
    stated. It stores a note and nothing else: a gene set the user wants in
    their workbench is created with ``create_workbench_gene_set``.

    A preference is keyed by its name, so stating one again replaces what the
    user said before. The reply says whether it stored a new memory or updated
    the one that name already holds.

    Args:
        kind: Which memory kind the entry belongs to. ``gene_set_note`` is a
            note about a gene set that already exists, never the gene set.
        name: Short, recall-friendly title, such as "P. falciparum kinome size".
        summary: One line shown in retrieval previews. Retrieval matches on it
            and on the content payload.
        content: The durable knowledge itself, as counts, identifiers or
            criteria a later turn can act on.
        tags: Retrieval tags, such as an organism, a technique or a dataset.
            The site id is added automatically, so do not repeat it here.
    """
    store_raw = ctx.deps.memory_store
    user_id = ctx.deps.user_id
    if store_raw is None or user_id is None:
        return with_summary(
            "memory store unavailable",
            "Memory is unavailable on this thread",
            ctx=ctx,
            status="warn",
        )
    mem_store = MemoryStore(store=store_raw)
    value = MemoryValue(
        kind=kind,
        name=name,
        summary=summary,
        tags=tags or [],
        site_id=ctx.deps.site_id,
        content=content,
        created_at=datetime.now(UTC),
    )
    key = _standing_key(kind, name)
    replaced = key is not None and (
        await mem_store.get(user_id=user_id, kind=kind, key=key) is not None
    )
    stored_key = await mem_store.put(user_id=user_id, value=value, key=key)
    action = "Updated" if replaced else "Stored"
    return with_summary(
        f"{action} {name} as {kind} under {stored_key}",
        f"{action} {name} as {kind}",
        ctx=ctx,
    )
