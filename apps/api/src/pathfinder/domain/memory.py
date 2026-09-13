"""The kinds of memory this application writes and reads across threads."""

from __future__ import annotations

import re
from typing import Literal, get_args

MemoryKind = Literal["gene_set_note", "strategy", "preference", "knowledge", "case"]

# The order a listing fills its buckets in.
MEMORY_KINDS: tuple[MemoryKind, ...] = get_args(MemoryKind)

# What the user states about their own work, which holds until they change it.
# A turn reads every one of these, whatever the request is about.
STANDING_MEMORY_KINDS: tuple[MemoryKind, ...] = ("preference",)


_NON_SLUG = re.compile(r"[^a-z0-9]+")

# The key is half of the store's primary key, which is a btree index row.
MAX_STANDING_KEY_LENGTH = 120


class UnnamedMemoryError(ValueError):
    """A standing memory whose name carries no letter and no digit."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"a standing memory is keyed by its name, and {name!r} has no "
            f"letter or digit to key it by",
        )
        self.name = name


def standing_memory_key(name: str) -> str:
    """The key a standing memory is written under, derived from its name.

    Two statements of one name are one memory, so the second replaces the
    first. Two names that share their first ``MAX_STANDING_KEY_LENGTH``
    characters are one memory too, which the bound accepts: a name is written
    for recall and is short. A name that carries no letter and no digit keys
    nothing.
    """
    slug = _NON_SLUG.sub("-", name.strip().lower()).strip("-")
    cut = slug[:MAX_STANDING_KEY_LENGTH].strip("-")
    if not cut:
        raise UnnamedMemoryError(name)
    return cut
