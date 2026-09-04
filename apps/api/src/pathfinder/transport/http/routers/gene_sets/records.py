"""Result browsing for a gene set: attributes, records, distributions, one record."""

from typing import Annotated

from fastapi import APIRouter, Depends

from pathfinder.services.wdk.step_results_models import (
    AttributesResponse,
    RecordDetailResponse,
)
from pathfinder.transport.http.deps import CurrentUser
from pathfinder.transport.http.schemas.step_results import (
    ClassifiedRecord,
    DistributionResponse,
    RecordQueryParams,
    RecordsMeta,
    RecordsPagination,
    RecordsResponse,
)
from pathfinder.transport.http.schemas.steps import RecordDetailRequest

from ._shared import NEEDS_WDK_LOGIN, gene_set_service, no_strategy, not_found

router = APIRouter()


@router.get(
    "/{gene_set_id}/results/attributes",
    response_model=AttributesResponse,
    dependencies=NEEDS_WDK_LOGIN,
)
async def get_gene_set_attributes(
    gene_set_id: str,
    user_id: CurrentUser,
) -> AttributesResponse:
    """Get available attributes for a gene set's record type."""
    try:
        svc = await gene_set_service().get_step_results_service(user_id, gene_set_id)
    except KeyError as exc:
        raise not_found(exc) from exc
    except ValueError as exc:
        raise no_strategy(exc) from exc
    return await svc.get_attributes()


@router.get(
    "/{gene_set_id}/results/records",
    response_model=RecordsResponse,
    dependencies=NEEDS_WDK_LOGIN,
)
async def get_gene_set_records(
    gene_set_id: str,
    user_id: CurrentUser,
    params: Annotated[RecordQueryParams, Depends()],
) -> RecordsResponse:
    """Get paginated result records for a gene set."""
    try:
        svc = await gene_set_service().get_step_results_service(user_id, gene_set_id)
    except KeyError as exc:
        raise not_found(exc) from exc
    except ValueError as exc:
        raise no_strategy(exc) from exc

    attr_list: list[str] | None = None
    if params.attributes:
        attr_list = [a.strip() for a in params.attributes.split(",") if a.strip()]

    if params.filter_attribute and params.filter_value is not None:
        answer = await svc.get_records(
            offset=0,
            limit=10_000,
            sort=params.sort,
            direction=params.sort_dir,
            attributes=attr_list,
        )
        filtered = [
            rec
            for rec in answer.records
            if rec.attribute_text(params.filter_attribute) == params.filter_value
        ]
        page = filtered[params.offset : params.offset + params.limit]
        return RecordsResponse(
            records=[
                ClassifiedRecord(
                    display_name=r.display_name,
                    id=r.id,
                    record_class_name=r.record_class_name,
                    attributes=r.attributes,
                    tables=r.tables,
                    table_errors=r.table_errors,
                )
                for r in page
            ],
            meta=RecordsMeta(
                total_count=len(filtered),
                display_total_count=len(filtered),
                response_count=len(page),
                pagination=RecordsPagination(
                    offset=params.offset, num_records=params.limit
                ),
                attributes=attr_list or [],
                tables=[],
            ),
        )

    answer = await svc.get_records(
        offset=params.offset,
        limit=params.limit,
        sort=params.sort,
        direction=params.sort_dir,
        attributes=attr_list,
    )
    return RecordsResponse(
        records=[
            ClassifiedRecord(
                display_name=r.display_name,
                id=r.id,
                record_class_name=r.record_class_name,
                attributes=r.attributes,
                tables=r.tables,
                table_errors=r.table_errors,
            )
            for r in answer.records
        ],
        meta=RecordsMeta(
            total_count=answer.meta.records_returned(),
            display_total_count=answer.meta.display_total_count,
            response_count=answer.meta.response_count,
            pagination=RecordsPagination(
                offset=params.offset, num_records=params.limit
            ),
            attributes=answer.meta.attributes,
            tables=answer.meta.tables,
        ),
    )


@router.get(
    "/{gene_set_id}/results/distributions/{attribute_name}",
    response_model=DistributionResponse,
    dependencies=NEEDS_WDK_LOGIN,
)
async def get_gene_set_distribution(
    gene_set_id: str,
    attribute_name: str,
    user_id: CurrentUser,
) -> DistributionResponse:
    """Get distribution data for an attribute using the byValue column reporter."""
    try:
        svc = await gene_set_service().get_step_results_service(user_id, gene_set_id)
    except KeyError as exc:
        raise not_found(exc) from exc
    except ValueError as exc:
        raise no_strategy(exc) from exc
    dist = await svc.get_distribution(attribute_name)
    return DistributionResponse(histogram=dist.histogram, statistics=dist.statistics)


@router.post(
    "/{gene_set_id}/results/record",
    response_model=RecordDetailResponse,
    dependencies=NEEDS_WDK_LOGIN,
)
async def get_gene_set_record_detail(
    gene_set_id: str,
    body: RecordDetailRequest,
    user_id: CurrentUser,
) -> RecordDetailResponse:
    """Get a single record's full details by primary key."""
    service = gene_set_service()
    try:
        gs = await service.get_for_user(user_id, gene_set_id)
        svc = await service.get_step_results_service(user_id, gene_set_id)
    except KeyError as exc:
        raise not_found(exc) from exc
    except ValueError as exc:
        raise no_strategy(exc) from exc

    pk_parts: list[dict[str, str]] = [
        {"name": part.name, "value": part.value} for part in body.primary_key
    ]
    return await svc.get_record_detail(pk_parts, gs.site_id)
