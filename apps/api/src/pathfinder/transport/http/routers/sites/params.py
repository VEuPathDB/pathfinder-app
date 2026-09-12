"""Parameter-related endpoints: dependent params, validation, param specs."""

from fastapi import APIRouter
from veupathdb.domain import SearchContext
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import (
    ParamSpecResponse,
    ValidationResponse,
    build_param_specs,
    build_param_specs_from_list,
)

from pathfinder.transport.http.deps import AvailableSite
from pathfinder.transport.http.schemas import (
    DependentParamsRequest,
    ParamSpecsRequest,
    SearchValidationRequest,
)

router = APIRouter(prefix="/api/v1/sites", tags=["sites"])


@router.post(
    "/{siteId}/searches/{recordType}/{searchName}/validate",
    response_model=ValidationResponse,
)
async def validate_search_params(
    siteId: AvailableSite,
    recordType: str,
    searchName: str,
    payload: SearchValidationRequest,
) -> ValidationResponse:
    """Validate search parameters (UI-friendly)."""
    return await catalog.validate_search_params(
        SearchContext(siteId, recordType, searchName),
        context_values=payload.context_values or {},
    )


@router.post(
    "/{siteId}/searches/{recordType}/{searchName}/param-specs",
    response_model=list[ParamSpecResponse],
)
async def get_param_specs_with_context(
    siteId: AvailableSite,
    recordType: str,
    searchName: str,
    payload: ParamSpecsRequest,
) -> list[ParamSpecResponse]:
    """Return normalized parameter specs, using contextual WDK vocab when provided."""
    response = await catalog.expand_search_details_with_params(
        SearchContext(siteId, recordType, searchName),
        payload.context_values or {},
    )
    return build_param_specs(response.search_data)


@router.post(
    "/{siteId}/searches/{recordType}/{searchName}/refreshed-dependent-params",
    response_model=list[ParamSpecResponse],
)
async def refresh_dependent_params(
    siteId: AvailableSite,
    recordType: str,
    searchName: str,
    payload: DependentParamsRequest,
) -> list[ParamSpecResponse]:
    """Refresh dependent parameter vocabularies after a param value changes."""
    params = await catalog.get_refreshed_dependent_params(
        SearchContext(siteId, recordType, searchName),
        parameter_name=payload.parameter_name,
        context_values=payload.context_values or {},
    )
    return build_param_specs_from_list(params)
