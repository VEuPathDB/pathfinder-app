"""A WDK step that holds exactly the genes a gene set stores.

A gene set records its membership. Browsing it through the step it was derived
from shows whatever that step returns now, which an edit to the source strategy
changes. Materializing the stored ids gives WDK something to report attributes
from without letting it decide who is in the set.
"""

from __future__ import annotations

import hashlib

from cachetools import LRUCache
from veupathdb.wdk.factory import get_strategy_api
from veupathdb.wdk.value_decoding import encode_params
from veupathdb.wdk.wdk_models import (
    NewStepSpec,
    WDKSearchConfig,
    WDKStepTree,
)
from veupathdb_mcp.wdk.gene_set_steps import (
    build_enrichment_params_from_gene_ids,
)

__all__ = ["frozen_step_cache_key", "frozen_step_id"]

_FROZEN_STEPS: LRUCache[str, int] = LRUCache(maxsize=64)


def frozen_step_cache_key(site_id: str, gene_ids: list[str]) -> str:
    """Key a materialized step by the membership it holds.

    Membership is a set, so order does not make a new step. The site is part
    of the key because the same locus tag names a different record elsewhere.
    """
    digest = hashlib.sha256("\n".join(sorted(set(gene_ids))).encode()).hexdigest()
    return f"{site_id}:{digest}"


async def frozen_step_id(
    site_id: str, gene_ids: list[str], record_type: str
) -> int | None:
    """Return a WDK step holding ``gene_ids``, or ``None`` when there are none."""
    if not gene_ids:
        return None
    key = frozen_step_cache_key(site_id, gene_ids)
    cached: int | None = _FROZEN_STEPS.get(key)
    if cached is not None:
        return cached

    (
        search_name,
        params,
        dataset_record_type,
    ) = await build_enrichment_params_from_gene_ids(site_id, gene_ids)
    api = get_strategy_api(site_id)
    created = await api.create_step(
        NewStepSpec(
            search_name=search_name,
            search_config=WDKSearchConfig(parameters=encode_params(params)),
        ),
        record_type or dataset_record_type,
    )
    # WDK refuses to run a step that belongs to no strategy, so the step is
    # held by an internal one that never appears in the user's workspace.
    await api.create_strategy(
        step_tree=WDKStepTree(step_id=created.id),
        name="Pathfinder gene set",
        description=None,
        is_internal=True,
    )
    _FROZEN_STEPS[key] = created.id
    return created.id
