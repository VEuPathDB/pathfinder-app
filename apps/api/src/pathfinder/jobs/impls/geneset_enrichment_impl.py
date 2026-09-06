"""Worker-side impl for ``run_gene_set_enrichment``.

Moved from ``ai/tools/standalone/workbench.py``. Runs ORA against a workbench
gene set on the verification worker; progress is emitted per enrichment phase
(lookup, dispatch, export, finalise).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from assistant_core.memory.store import MemoryStore
from veupathdb_mcp.wdk.enrichment.types import (
    ALL_ENRICHMENT_ANALYSIS_TYPES,
    EnrichmentAnalysisType,
)

from pathfinder.ai.graph.runtime import Context
from pathfinder.jobs.progress import TaskProgressEmitter
from pathfinder.services.workbench.gene_sets import (
    get_gene_set,
    run_gene_set_enrichment,
)


async def run_gene_set_enrichment_impl(
    *,
    context: Context,
    task_id: UUID,
    progress: TaskProgressEmitter,
    memory_store: MemoryStore | None,
    gene_set_id: str,
    enrichment_types: list[str] | None = None,
    **_extra: Any,
) -> dict[str, Any]:
    """Run enrichment analysis on a workbench gene set."""
    del context, task_id, memory_store

    await progress.update(
        percent=0.0,
        message=f"Loading gene set {gene_set_id}",
        data={"gene_set_id": gene_set_id},
    )
    gs = await get_gene_set(gene_set_id)
    if gs is None:
        msg = f"gene set {gene_set_id} does not exist"
        raise LookupError(msg)

    types: list[EnrichmentAnalysisType] = (
        [t for t in ALL_ENRICHMENT_ANALYSIS_TYPES if t in enrichment_types]
        if enrichment_types
        else list(ALL_ENRICHMENT_ANALYSIS_TYPES)
    )
    await progress.update(
        percent=0.2,
        message=f"Running enrichment ({len(types)} analyses)",
        data={"analyses": list(types), "gene_count": len(gs.gene_ids)},
    )

    summary = await run_gene_set_enrichment(gs, types)
    await progress.update(
        percent=0.9,
        message="Finalising enrichment summary",
        data=None,
    )

    result: dict[str, Any] = dict(summary)
    result["geneSetId"] = gene_set_id
    result["geneSetName"] = gs.name
    result["geneCount"] = len(gs.gene_ids)

    await progress.update(
        percent=1.0,
        message="Enrichment complete",
        data=None,
    )
    return result
