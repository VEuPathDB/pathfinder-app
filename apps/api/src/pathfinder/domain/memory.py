"""The kinds of memory this application writes and reads across threads."""

from __future__ import annotations

from typing import Literal, get_args

MemoryKind = Literal["gene_set_note", "strategy", "preference", "knowledge", "case"]

# The order a listing fills its buckets in.
MEMORY_KINDS: tuple[MemoryKind, ...] = get_args(MemoryKind)

# What the user states about their own work, which holds until they change it.
# A turn reads every one of these, whatever the request is about.
STANDING_MEMORY_KINDS: tuple[MemoryKind, ...] = ("preference",)
