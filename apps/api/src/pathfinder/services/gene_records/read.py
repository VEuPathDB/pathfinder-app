"""One gene record on one site, reduced to the facts an answer states."""

from __future__ import annotations

from typing import Annotated

from assistant_core.graph.tool_summary import count_noun
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
)
from veupathdb.errors import VEuPathDBError, WDKError
from veupathdb.wdk import (
    StrategyAPI,
    WDKRecordInstance,
    get_site,
    get_strategy_api,
)
from veupathdb_mcp.wdk import get_gene_expression_summary, order_primary_key

from pathfinder.platform.errors import NotFoundError

GENE_RECORD_TYPE = "gene"
ORTHOLOGS_TABLE = "Orthologs"
# An answer names the orthologs it can read; the total says how many there are.
MAX_ORTHOLOG_ROWS = 20
_NOT_FOUND_STATUS = 404

# The gene attributes the summary reads, in the order the site is asked for
# them. A name the record type does not declare makes WDK answer a 500, so
# only the declared ones are asked for.
WANTED_ATTRIBUTES = (
    "organism",
    "product",
    "name",
    "chromosome",
    "exon_count",
    "transcript_count",
)


class UnknownGeneRecordError(NotFoundError):
    """A gene id the site holds no record for."""

    def __init__(self, site_id: str, gene_id: str) -> None:
        self.gene_id = gene_id
        super().__init__(
            title="Gene record not found",
            detail=f"{gene_id!r} names no gene record on {site_id}.",
        )


def _cell_text(value: object) -> object:
    """A table cell is text, or a link that carries its text."""
    match value:
        case None:
            return ""
        case {"displayText": text}:
            return text
        case other:
            return other


def _counted(value: object) -> object:
    """A count attribute that is not a whole number names no count."""
    text = str(value or "").strip()
    return text if text.isdigit() else None


CellText = Annotated[str, BeforeValidator(_cell_text)]
OptionalCount = Annotated[int | None, BeforeValidator(_counted)]


class OrthologRow(CamelModel):
    """One ortholog the record's table lists."""

    model_config = ConfigDict(frozen=True)

    organism: str
    gene_id: str


class ExpressionSummary(CamelModel):
    """The site's own summary of one gene's expression."""

    model_config = ConfigDict(frozen=True)

    headline: str
    paragraph: str = ""
    experiments: int | None = None
    covers_part_of_the_experiments: bool = False


class GeneRecordSummary(CamelModel):
    """What one site's gene record states about one gene."""

    model_config = ConfigDict(frozen=True)

    site_id: str
    gene_id: str
    record_url: str
    organism: str = ""
    product: str = ""
    gene_name: str | None = None
    chromosome: str | None = None
    exon_count: int | None = None
    transcript_count: int | None = None
    orthologs: list[OrthologRow] = Field(default_factory=list)
    ortholog_count: int = 0
    expression: ExpressionSummary | None = None

    def summary_line(self) -> str:
        """The one line the thread shows for this read."""
        stated = [self.product or "no product on the record"]
        if self.exon_count is not None:
            stated.append(count_noun(self.exon_count, "exon"))
        if self.chromosome:
            stated.append(f"chromosome {self.chromosome}")
        if self.ortholog_count:
            stated.append(count_noun(self.ortholog_count, "ortholog"))
        return f"{self.gene_id}: {', '.join(stated)}"


class GeneRecordType(CamelModel):
    """What one site declares about its gene record, read once per site."""

    model_config = ConfigDict(frozen=True)

    attribute_names: frozenset[str]
    primary_key_refs: tuple[str, ...]

    @field_validator("primary_key_refs")
    @classmethod
    def _the_wdk_key_when_the_site_declares_none(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        """A gene record is keyed by its source id and its project."""
        return value or ("source_id", "project_id")


class _GeneAttributes(BaseModel):
    """The gene attributes the summary reads, under their WDK names."""

    model_config = ConfigDict(extra="ignore")

    organism: str = ""
    product: str = ""
    name: str | None = None
    chromosome: str | None = None
    exon_count: OptionalCount = None
    transcript_count: OptionalCount = None


class _OrthologTableRow(BaseModel):
    """One row of the record's Orthologs table."""

    model_config = ConfigDict(extra="ignore")

    organism: CellText = ""
    ortho_gene_source_id: CellText = ""


class _RecordTables(BaseModel):
    """The tables the record read asked for."""

    model_config = ConfigDict(extra="ignore")

    orthologs: list[_OrthologTableRow] = Field(
        default_factory=list,
        alias=ORTHOLOGS_TABLE,
    )


_gene_record_types: dict[str, GeneRecordType] = {}


async def gene_record_type(api: StrategyAPI, site_id: str) -> GeneRecordType:
    """What ``site_id`` declares about its gene record, from cache after the
    first read."""
    known = _gene_record_types.get(site_id)
    if known is not None:
        return known
    info = await api.get_record_type_info(GENE_RECORD_TYPE)
    fields = info.attributes or list((info.attributes_map or {}).values())
    declared = GeneRecordType(
        attribute_names=frozenset(field.name for field in fields),
        primary_key_refs=tuple(info.primary_key_column_refs),
    )
    _gene_record_types[site_id] = declared
    return declared


async def _expression_of(site_id: str, gene_id: str) -> ExpressionSummary | None:
    """The site's expression summary for the gene, where it generated one."""
    try:
        found = await get_gene_expression_summary(site_id, gene_id)
    # A site that serves no expression report holds no summary for any gene.
    except VEuPathDBError, OSError:
        return None
    if found.summary is None:
        return None
    return ExpressionSummary(
        headline=found.summary.headline,
        paragraph=found.summary.one_paragraph_summary,
        experiments=found.num_experiments,
        covers_part_of_the_experiments=bool(found.based_on_incomplete_data),
    )


def _attribute_texts(record: WDKRecordInstance) -> dict[str, str]:
    """Each wanted attribute the record carries, as comparable text."""
    read_texts = ((name, record.attribute_text(name)) for name in WANTED_ATTRIBUTES)
    return {name: text for name, text in read_texts if text is not None}


async def read_gene_record(site_id: str, gene_id: str) -> GeneRecordSummary:
    """The record ``site_id`` holds for ``gene_id``, under the caller's token."""
    return await read_the_gene_record(get_strategy_api(site_id), site_id, gene_id)


async def read_the_gene_record(
    api: StrategyAPI,
    site_id: str,
    gene_id: str,
) -> GeneRecordSummary:
    """The gene record one site's API answers, as a summary."""
    site = get_site(site_id)
    declared = await gene_record_type(api, site_id)
    try:
        record = await api.get_single_record(
            GENE_RECORD_TYPE,
            order_primary_key(
                [{"name": "source_id", "value": gene_id}],
                list(declared.primary_key_refs),
                {"project_id": site.project_id},
            ),
            attributes=[
                name for name in WANTED_ATTRIBUTES if name in declared.attribute_names
            ],
            tables=[ORTHOLOGS_TABLE],
        )
    except WDKError as refused:
        if refused.status != _NOT_FOUND_STATUS:
            raise
        raise UnknownGeneRecordError(site_id, gene_id) from refused
    stated = _GeneAttributes.model_validate(_attribute_texts(record))
    rows = _RecordTables.model_validate(record.tables).orthologs
    return GeneRecordSummary(
        site_id=site_id,
        gene_id=gene_id,
        record_url=f"{site.web_base_url}/app/record/{GENE_RECORD_TYPE}/{gene_id}",
        organism=stated.organism,
        product=stated.product,
        gene_name=stated.name,
        chromosome=stated.chromosome,
        exon_count=stated.exon_count,
        transcript_count=stated.transcript_count,
        orthologs=[
            OrthologRow(organism=row.organism, gene_id=row.ortho_gene_source_id)
            for row in rows[:MAX_ORTHOLOG_ROWS]
        ],
        ortholog_count=len(rows),
        expression=await _expression_of(site_id, gene_id),
    )
