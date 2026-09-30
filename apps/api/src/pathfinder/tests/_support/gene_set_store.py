"""A gene set store double that holds its sets in a dict, for unit tests.

A method it does not override reaches the database, which a unit test refuses.
"""

from collections.abc import Awaitable, Callable
from dataclasses import replace

from pathfinder.services.gene_sets.store import GeneSetStore
from pathfinder.services.gene_sets.types import GeneSet


class InMemoryGeneSetStore(GeneSetStore):
    """Holds a copy of each saved set, as a table holds a row."""

    def __init__(self) -> None:
        self.rows: dict[str, GeneSet] = {}

    async def save(self, gene_set: GeneSet) -> None:
        self.rows[gene_set.id] = replace(gene_set, gene_ids=list(gene_set.gene_ids))

    async def get(self, gene_set_id: str) -> GeneSet | None:
        row = self.rows.get(gene_set_id)
        return None if row is None else replace(row, gene_ids=list(row.gene_ids))

    async def set_vdi_id(self, gene_set_id: str, vdi_id: str | None) -> None:
        self.rows[gene_set_id].vdi_id = vdi_id


def keep_saved(kept: list[GeneSet]) -> Callable[[GeneSet], Awaitable[None]]:
    """A save that appends each set to ``kept``."""

    async def _save(gene_set: GeneSet) -> None:
        kept.append(gene_set)

    return _save
