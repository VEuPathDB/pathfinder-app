from __future__ import annotations

from datetime import datetime
from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field

from pathfinder.domain.memory import MemoryKind


class MemoryValue(CamelModel):
    """One stored memory on the wire.

    The runtime holds a kind to a name's shape; which names exist is this
    application's, so the wire names them.
    """

    kind: MemoryKind
    name: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    site_id: str | None = None
    content: dict[str, object]
    auto_retrieve: bool = True
    source_conversation_id: UUID | None = None
    created_at: datetime
    last_used_at: datetime | None = None


class MemoryItem(CamelModel):
    key: str
    value: MemoryValue


class MemoryListResponse(CamelModel):
    """Paginated list, grouped by namespace.

    ``page_size`` and ``offset`` echo the query params. ``has_more`` is
    ``True`` when at least one namespace returned a full page (i.e. more
    rows likely exist at the next offset). Clients use this to decide
    whether to render a "load more" affordance without an additional
    count query.
    """

    gene_sets: list[MemoryItem]
    strategies: list[MemoryItem]
    preferences: list[MemoryItem]
    knowledge: list[MemoryItem]
    cases: list[MemoryItem]
    page_size: int
    offset: int
    has_more: bool


class MemoryEditRequest(CamelModel):
    name: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    content: dict[str, object] | None = None
    auto_retrieve: bool | None = None


class MemorySearchResponse(CamelModel):
    hits: list[MemoryItem]
