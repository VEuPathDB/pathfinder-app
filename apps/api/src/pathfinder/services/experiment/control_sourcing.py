"""Build control gene lists for scored experiments from any source.

A scored experiment needs positive/negative control gene-id lists. In a chat,
the Lead sources these from: pasted text, an uploaded CSV/TSV file, a saved
workbench gene set, or another strategy's results. This module normalizes all
of those to validated ``list[str]`` and persists a ControlSet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb_mcp.gene_lookup import resolve_gene_ids

from pathfinder.platform.errors import NotFoundError
from pathfinder.services.eval import get_strategy_gene_ids
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import get_gene_set_store


@dataclass
class ResolvedControls:
    """Outcome of validating raw gene IDs against WDK."""

    valid_ids: list[str] = field(default_factory=list)
    unresolved_ids: list[str] = field(default_factory=list)


async def validate_control_ids(
    site_id: str,
    gene_ids: list[str],
    *,
    record_type: str = "transcript",
) -> ResolvedControls:
    """Validate gene IDs against WDK, splitting recognized from unresolved.

    Lets the Lead warn the user about typos/aliases before using a list as
    controls. Order-preserving and deduped.
    """
    cleaned = [g.strip() for g in gene_ids if g.strip()]
    deduped = list(dict.fromkeys(cleaned))
    if not deduped:
        return ResolvedControls()
    result = await resolve_gene_ids(site_id, deduped, record_type=record_type)
    recognized = {r.gene_id for r in result.records}
    return ResolvedControls(
        valid_ids=[g for g in deduped if g in recognized],
        unresolved_ids=[g for g in deduped if g not in recognized],
    )


async def control_ids_from_saved_gene_set(
    user_id: UUID,
    gene_set_id: str,
) -> list[str]:
    """Pull the gene-id list out of a saved workbench gene set."""
    service = GeneSetService(get_gene_set_store())
    gene_set = await service.get_for_user(user_id, gene_set_id)
    return list(gene_set.gene_ids)


@dataclass
class StrategyControls:
    """Gene IDs imported from another strategy's results."""

    gene_ids: list[str] = field(default_factory=list)
    error: str | None = None


async def control_ids_from_strategy(
    session: AsyncSession,
    strategy_id: UUID,
    site_id: str,
    user_id: UUID,
) -> StrategyControls:
    """Import a strategy's result gene IDs (to use as positive or negative
    controls). Returns an error message rather than raising when the strategy
    is not the caller's or has no linked WDK results."""
    try:
        result = await get_strategy_gene_ids(session, strategy_id, site_id, user_id)
    except NotFoundError:
        return StrategyControls(error="Strategy not found")
    return StrategyControls(gene_ids=list(result.gene_ids), error=result.error)
