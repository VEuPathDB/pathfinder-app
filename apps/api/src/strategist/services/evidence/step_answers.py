from __future__ import annotations

from collections.abc import Sequence

from strategist.domain.step_membership import StepHolds
from strategist.services.gene_sets.step_genes import first_step_gene_ids


async def ids_the_step_holds(
    site_id: str, wdk_step_id: int, *, gene_ids: Sequence[str], listed_at_most: int
) -> StepHolds:
    asked = frozenset(gene_ids)
    listed = await first_step_gene_ids(site_id, wdk_step_id, limit=listed_at_most)
    inside = asked & frozenset(listed.gene_ids)
    whole = len(listed.gene_ids) >= listed.total
    return StepHolds(inside=inside, outside=asked - inside if whole else frozenset())
