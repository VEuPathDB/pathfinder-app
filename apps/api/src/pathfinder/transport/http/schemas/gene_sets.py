"""HTTP request/response schemas for gene sets."""

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from veupathdb.domain.parameters import ParamValue

from pathfinder.services.gene_sets.types import GeneSetSource
from pathfinder.transport.http.schemas.site_id import SiteId


class GeneSetResponse(CamelModel):
    """A gene set, as returned to the client."""

    id: str
    name: str
    site_id: str
    gene_ids: list[str]
    source: GeneSetSource
    gene_count: int
    membership_digest: str
    """Names the genes this set holds now."""
    wdk_strategy_id: int | None = Field(None)
    wdk_step_id: int | None = Field(None)
    search_name: str | None = Field(None)
    record_type: str | None = Field(None)
    parameters: dict[str, ParamValue] | None = None
    created_at: str
    step_count: int = Field(1)
    vdi_id: str | None = None
    """The VEuPathDB user dataset this set was published to, when it was."""


# A model's docstring is published as its schema description, so these two
# stay undocumented until the described text is part of the contract.
class GeneSetImportRequest(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    site_id: SiteId
    raw_text: str


class GeneSetExportResponse(CamelModel):
    export_id: str
    filename: str
    content_type: str
    url: str
