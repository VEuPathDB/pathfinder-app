from __future__ import annotations

from typing import Annotated

from assistant_core.memory.store import MemoryStore, StoredMemory
from assistant_core.memory.tombstones import TombstoneRepository
from assistant_core.platform.db import async_session_factory
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from langgraph.store.postgres.aio import AsyncPostgresStore

from pathfinder.domain.memory import MEMORY_KINDS, MemoryKind
from pathfinder.transport.http.deps import CurrentUser
from pathfinder.transport.http.schemas.memories import (
    MemoryEditRequest,
    MemoryItem,
    MemoryListResponse,
    MemorySearchResponse,
    MemoryValue,
)

router = APIRouter(prefix="/api/v1/memories", tags=["memories"])

_MAX_PAGE_LIMIT: int = 200
_DEFAULT_PAGE_LIMIT: int = 50


def _store(request: Request) -> MemoryStore:
    raw: AsyncPostgresStore = request.app.state.memory_store
    return MemoryStore(store=raw)


def _tombstones() -> TombstoneRepository:
    return TombstoneRepository(session_factory=async_session_factory)


def _to_item(stored: StoredMemory) -> MemoryItem:
    return MemoryItem(
        key=stored.key,
        value=MemoryValue.model_validate(stored.value, from_attributes=True),
    )


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    request: Request,
    user_id: CurrentUser,
    limit: Annotated[
        int,
        Query(ge=1, le=_MAX_PAGE_LIMIT, description="Per-namespace page size"),
    ] = _DEFAULT_PAGE_LIMIT,
    offset: Annotated[int, Query(ge=0, description="Per-namespace offset")] = 0,
) -> MemoryListResponse:
    store = _store(request)
    buckets: dict[MemoryKind, list[MemoryItem]] = {}
    any_full_page = False
    for kind in MEMORY_KINDS:
        stored = await store.list_all(
            user_id=user_id,
            kind=kind,
            limit=limit,
            offset=offset,
        )
        buckets[kind] = [_to_item(s) for s in stored]
        # If any namespace returned a full page, more rows may exist at
        # the next offset — the client should show "load more".
        if len(stored) >= limit:
            any_full_page = True
    return MemoryListResponse(
        gene_set_notes=buckets["gene_set_note"],
        strategies=buckets["strategy"],
        preferences=buckets["preference"],
        knowledge=buckets["knowledge"],
        cases=buckets["case"],
        page_size=limit,
        offset=offset,
        has_more=any_full_page,
    )


@router.get("/search", response_model=MemorySearchResponse)
async def search_memories(
    request: Request,
    user_id: CurrentUser,
    q: Annotated[str, Query(min_length=1, max_length=500)],
) -> MemorySearchResponse:
    store = _store(request)
    hits: list[MemoryItem] = []
    for kind in MEMORY_KINDS:
        stored = await store.semantic_search(
            user_id=user_id,
            kind=kind,
            query=q,
            top_k=5,
        )
        hits.extend(_to_item(s) for s in stored)
    return MemorySearchResponse(hits=hits[:10])


@router.patch("/{key}", response_model=MemoryItem)
async def edit_memory(
    key: str,
    kind: Annotated[MemoryKind, Query()],
    body: MemoryEditRequest,
    request: Request,
    user_id: CurrentUser,
) -> MemoryItem:
    store = _store(request)
    current = await store.get(user_id=user_id, kind=kind, key=key)
    if current is None:
        raise HTTPException(status_code=404, detail="memory not found")
    updates = {
        k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None
    }
    updated = current.value.model_copy(update=updates)
    await store.put(user_id=user_id, value=updated, key=key)
    return MemoryItem(
        key=key, value=MemoryValue.model_validate(updated, from_attributes=True)
    )


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    key: str,
    kind: Annotated[MemoryKind, Query()],
    request: Request,
    user_id: CurrentUser,
) -> Response:
    store = _store(request)
    tombstones = _tombstones()
    current = await store.get(user_id=user_id, kind=kind, key=key)
    if current is None:
        raise HTTPException(status_code=404, detail="memory not found")
    await tombstones.tombstone(user_id=user_id, value=current.value)
    await store.delete(user_id=user_id, kind=kind, key=key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
