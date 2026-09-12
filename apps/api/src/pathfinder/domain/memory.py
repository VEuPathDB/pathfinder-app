"""The kinds of memory this application writes and reads across threads."""

from __future__ import annotations

from typing import Literal, get_args

MemoryKind = Literal["gene_set", "strategy", "preference", "knowledge", "case"]

# The order a listing fills its buckets in.
MEMORY_KINDS: tuple[MemoryKind, ...] = get_args(MemoryKind)
