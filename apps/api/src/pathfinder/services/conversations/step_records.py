"""The genes one step of a thread's strategy answers on its site, one page at a time."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb import strip_html_tags
from veupathdb.errors import ValidationError
from veupathdb.wdk import WDKRecordInstance, get_site, get_strategy_api
from veupathdb_mcp.wdk import view_filters_for

from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.errors import AppError, ErrorCode, NotFoundError
from pathfinder.services.conversations.authz import get_owned_thread_or_404
from pathfinder.services.conversations.responses import (
    StepRecord,
    StepRecordsResponse,
)
from pathfinder.services.gene_records.read import gene_record_url
from pathfinder.services.gene_sets.step_genes import extract_gene_id
from pathfinder.services.strategies.session_factory import (
    build_strategy_session,
    persisted_graph,
)
from pathfinder.services.strategies.sync_state import ensure_sync_state


@dataclass(frozen=True)
class StepPage:
    """Which step to read, by its graph id, and which page of its genes."""

    step_id: str
    offset: int
    limit: int


# The product column a gene answer names, by record type.
_PRODUCT_ATTRIBUTE = {"transcript": "gene_product", "gene": "product"}


def _record(site_id: str, record: WDKRecordInstance, product: str) -> StepRecord:
    gene_id = extract_gene_id(record) or record.display_name
    return StepRecord(
        gene_id=gene_id,
        organism=strip_html_tags(record.attribute_text("organism")) or None,
        product=strip_html_tags(record.attribute_text(product)) or None,
        record_url=gene_record_url(site_id, gene_id),
    )


async def read_step_records(
    session: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
    *,
    site_id: str,
    page: StepPage,
) -> StepRecordsResponse:
    """One page of the genes a step answers, one row per gene."""
    step_id = page.step_id
    conversation, strategy = await get_owned_thread_or_404(
        ConversationRepository(session), conversation_id, user_id
    )
    strategy_session = build_strategy_session(
        site_id=site_id, strategy_graph=persisted_graph(conversation, strategy)
    )
    graph = strategy_session.get_graph(None)
    if graph is None or step_id not in graph.steps:
        raise NotFoundError(
            code=ErrorCode.STEP_NOT_FOUND,
            title="step not found",
            detail=f"step {step_id!r} not found in conversation {conversation_id}",
        )
    sync_state = ensure_sync_state(strategy_session)
    wdk_step_id = sync_state.wdk_step_ids.get(step_id)
    if wdk_step_id is None or sync_state.wdk_strategy_id is None:
        raise AppError(
            code=ErrorCode.INVALID_STRATEGY,
            title="The step is not on the site yet",
            status=409,
            detail=f"Step {step_id!r} is not on the site yet, so it has no results.",
        )
    record_type = graph.record_type or ""
    product = _PRODUCT_ATTRIBUTE.get(record_type)
    if product is None:
        raise ValidationError(
            title="The step does not answer genes",
            detail=f"A {record_type} record is not a gene.",
        )
    answer = await get_strategy_api(site_id).get_step_answer(
        wdk_step_id,
        attributes=["primary_key", "organism", product],
        pagination={"offset": page.offset, "numRecords": page.limit},
        view_filters=view_filters_for(record_type),
    )
    return StepRecordsResponse(
        step_id=step_id,
        wdk_step_id=wdk_step_id,
        total=answer.meta.records_returned(),
        offset=page.offset,
        limit=page.limit,
        record_type=record_type,
        step_url=get_site(site_id).strategy_url(
            sync_state.wdk_strategy_id, wdk_step_id
        ),
        records=[_record(site_id, record, product) for record in answer.records],
    )
