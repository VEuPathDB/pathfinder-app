"""Gene Set data model."""

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Self
from uuid import UUID

from assistant_core.platform.context import calling_application
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from veupathdb.domain.parameters import ParamValue
from veupathdb_mcp.wdk import GeneSetWdkContext
from veupathdb_mcp.wdk.enrichment import EnrichmentResult

GeneSetSource = Literal["strategy", "paste", "upload", "derived", "saved"]


class GeneSetMembership(CamelModel):
    """The gene ids a set holds, named by a digest of them.

    Two sets of the same size are different sets, so the count alone does not
    tell one membership from another.
    """

    model_config = ConfigDict(frozen=True)

    gene_count: int
    digest: str

    @classmethod
    def of(cls, gene_ids: Iterable[str]) -> Self:
        """Name the membership these gene ids make.

        Membership is a set, so order and repetition change nothing.
        """
        unique = sorted(set(gene_ids))
        return cls(
            gene_count=len(unique),
            digest=hashlib.sha256("\n".join(unique).encode()).hexdigest(),
        )


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

    def take_wdk_context(self, ctx: GeneSetWdkContext, *, step_count: int) -> None:
        """Adopt a resolved WDK context whole.

        Every field of the context is one field of the set, so a take replaces
        all of them and leaves none of the previous resolution behind.
        """
        self.wdk_strategy_id = ctx.wdk_strategy_id
        self.wdk_step_id = ctx.wdk_step_id
        self.search_name = ctx.search_name
        self.record_type = ctx.record_type
        self.parameters = ctx.parameters
        self.step_count = step_count
