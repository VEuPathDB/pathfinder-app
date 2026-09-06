"""HTTP endpoints for experiment results: records, attributes, distributions."""

from typing import Annotated

from fastapi import APIRouter, Depends
from veupathdb_mcp.wdk.step_results import (
    StepResultsService,
    step_results_service,
)
from veupathdb_mcp.wdk.step_results_models import (
    AttributesResponse,
    RecordDetailResponse,
)

from pathfinder.platform.errors import NotFoundError
from pathfinder.services.experiment.classification import classify_records
from pathfinder.transport.http.deps import (
    CurrentUser,
    ExperimentDep,
    require_registered_wdk_identity,
)
from pathfinder.transport.http.schemas.step_results import (
    ClassifiedRecord,
    DistributionResponse,
    RecordQueryParams,
    RecordsMeta,
    RecordsPagination,
    RecordsResponse,
)
from pathfinder.transport.http.schemas.steps import RecordDetailRequest

# Every route here reads or writes the experiment's WDK strategy.
router = APIRouter(dependencies=[Depends(require_registered_wdk_identity)])


def _require_step(exp: ExperimentDep) -> StepResultsService:
    """Builds a StepResultsService. An experiment with no WDK step raises not found."""
    if not exp.wdk_step_id:
        raise NotFoundError(title="No WDK strategy for this experiment")
    return step_results_service(
        site_id=exp.config.site_id,
        step_id=exp.wdk_step_id,
        record_type=exp.config.record_type,
    )


@router.get("/{experiment_id}/results/attributes", response_model=AttributesResponse)
async def get_experiment_attributes(
    exp: ExperimentDep,
    user_id: CurrentUser,
) -> AttributesResponse:
    """Returns the available attributes for the experiment record type."""
    svc = step_results_service(
        site_id=exp.config.site_id,
        step_id=exp.wdk_step_id or 0,
        record_type=exp.config.record_type,
    )
    return await svc.get_attributes()


@router.get("/{experiment_id}/results/records", response_model=RecordsResponse)
async def get_experiment_records(
    exp: ExperimentDep,
    user_id: CurrentUser,
    params: Annotated[RecordQueryParams, Depends()],
) -> RecordsResponse:
    """Returns one page of classified result records."""
    if not exp.wdk_step_id or not exp.wdk_strategy_id:
        raise NotFoundError(
            title="No WDK strategy",
            detail="This experiment has no persisted WDK strategy for result browsing.",
        )

    svc = _require_step(exp)
    attr_list: list[str] | None = None
    if params.attributes:
        attr_list = [a.strip() for a in params.attributes.split(",") if a.strip()]

    tp_ids = {g.id for g in exp.true_positive_genes}
    fp_ids = {g.id for g in exp.false_positive_genes}
    fn_ids = {g.id for g in exp.false_negative_genes}
    tn_ids = {g.id for g in exp.true_negative_genes}

    if params.filter_attribute and params.filter_value is not None:
        answer = await svc.get_records(
            offset=0,
            limit=10_000,
            sort=params.sort,
            direction=params.sort_dir,
            attributes=attr_list,
        )
        filtered_records = [
            rec
            for rec in answer.records
            if rec.attribute_text(params.filter_attribute) == params.filter_value
        ]
        classified_dicts = classify_records(
            filtered_records,
            tp_ids=tp_ids,
            fp_ids=fp_ids,
            fn_ids=fn_ids,
            tn_ids=tn_ids,
        )
        page = classified_dicts[params.offset : params.offset + params.limit]
        return RecordsResponse(
            records=[ClassifiedRecord.model_validate(r) for r in page],
            meta=RecordsMeta(
                total_count=len(classified_dicts),
                display_total_count=len(classified_dicts),
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
    classified_dicts = classify_records(
        answer.records,
        tp_ids=tp_ids,
        fp_ids=fp_ids,
        fn_ids=fn_ids,
        tn_ids=tn_ids,
    )
    return RecordsResponse(
        records=[ClassifiedRecord.model_validate(r) for r in classified_dicts],
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


@router.post("/{experiment_id}/results/record", response_model=RecordDetailResponse)
async def get_experiment_record_detail(
    exp: ExperimentDep,
    body: RecordDetailRequest,
    user_id: CurrentUser,
) -> RecordDetailResponse:
    """Returns the full detail of one record, selected by primary key."""
    pk_parts: list[dict[str, str]] = [
        {"name": part.name, "value": part.value} for part in body.primary_key
    ]

    svc = step_results_service(
        site_id=exp.config.site_id,
        step_id=exp.wdk_step_id or 0,
        record_type=exp.config.record_type,
    )
    return await svc.get_record_detail(pk_parts, exp.config.site_id)


@router.get(
    "/{experiment_id}/results/distributions/{attribute_name}",
    response_model=DistributionResponse,
)
async def get_experiment_distribution(
    exp: ExperimentDep,
    attribute_name: str,
    user_id: CurrentUser,
) -> DistributionResponse:
    """Returns the distribution of one attribute from the byValue column reporter."""
    svc = _require_step(exp)
    dist = await svc.get_distribution(attribute_name)
    return DistributionResponse(histogram=dist.histogram, statistics=dist.statistics)
