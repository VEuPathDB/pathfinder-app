"""Gene Set data model."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from assistant_core.platform.context import calling_application
from veupathdb.domain.parameters.values import ParamValue
from veupathdb_mcp.wdk.enrichment import EnrichmentResult

GeneSetSource = Literal["strategy", "paste", "upload", "derived", "saved"]


@dataclass
class GeneSet:
    """A named collection of gene IDs for analysis."""

    id: str
    name: str
    site_id: str
    gene_ids: list[str]
    source: GeneSetSource
    user_id: UUID | None = None
    # The application the set was created under; it owns the set with the user.
    application_id: str = field(default_factory=calling_application)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    wdk_strategy_id: int | None = None
    wdk_step_id: int | None = None
    search_name: str | None = None
    record_type: str | None = None
    parameters: dict[str, ParamValue] | None = None
    parent_set_ids: list[str] = field(default_factory=list)
    operation: str | None = None  # "intersect" | "union" | "minus"
    step_count: int = 1
    vdi_id: str | None = None
    """The VEuPathDB user dataset this set was published to, when it was."""
    enrichment_results: list[EnrichmentResult] = field(default_factory=list)
    """Enrichment the researcher has already run on this set.

    Computing it is a slow WDK round trip; not storing it meant reopening the
    workbench threw the analysis away and it had to be paid for again.
    """
