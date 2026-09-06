r"""Builders for the ``DataChunk``\ s that carry strategy telemetry to the
frontend as data parts on the assistant message."""

from __future__ import annotations

from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb_mcp.wdk.enrichment.types import EnrichmentResult

from pathfinder.ai.lead.ledger import InvestigationLedger
from pathfinder.ai.stream_part_payloads import EnrichmentResultsChunk


def enrichment_results_event(
    *,
    task_id: UUID,
    gene_set_id: str,
    gene_set_name: str,
    gene_count: int,
    results: list[EnrichmentResult],
    downloads: dict[str, str | int] | None = None,
) -> DataChunk:
    return DataChunk(
        type="data-enrichment-results",
        data=EnrichmentResultsChunk(
            task_id=str(task_id),
            gene_set_id=gene_set_id,
            gene_set_name=gene_set_name,
            gene_count=gene_count,
            results=results,
            downloads=downloads,
        ).model_dump(by_alias=True, mode="json"),
    )


class StrategyRevisionPayload(CamelModel):
    """Payload for the strategy-revision chunk. The revision is a fingerprint
    of the strategy that the turn describes.
    """

    revision: str


def strategy_revision_event(*, revision: str) -> DataChunk:
    return DataChunk(
        type="data-strategy-revision",
        data=StrategyRevisionPayload(revision=revision).model_dump(
            by_alias=True,
            mode="json",
        ),
    )


def ledger_update_event(*, ledger: InvestigationLedger) -> DataChunk:
    """Report a snapshot of the investigation ledger."""
    return DataChunk(
        type="data-ledger-update",
        data=ledger.model_dump(by_alias=True, mode="json"),
    )
