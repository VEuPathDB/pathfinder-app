"""The catalog builders the spanning tests need, beside the tests that use them."""

from __future__ import annotations

from veupathdb.domain.search import SearchContext
from veupathdb.json_types import JSONObject
from veupathdb.wdk.wdk_models import (
    StepValidation,
    WDKSearch,
    WDKSearchResponse,
)
from veupathdb.wdk.wdk_parameters import (
    WDKParameter,
)
from veupathdb_mcp.catalog.param_validation import ValidationCallbacks


def wdk_search_response(
    search_name: str,
    parameters: list[WDKParameter],
    *,
    level: str = "SEMANTIC",
    is_valid: bool = True,
    errors: JSONObject | None = None,
    query_name: str = "",
) -> WDKSearchResponse:
    return WDKSearchResponse(
        search_data=WDKSearch(
            url_segment=search_name,
            full_name=search_name,
            display_name=search_name,
            query_name=query_name,
            param_names=[p.name for p in parameters],
            parameters=parameters,
        ),
        validation=StepValidation.model_validate(
            {"level": level, "isValid": is_valid, "errors": errors}
        ),
    )


def validation_callbacks() -> ValidationCallbacks:
    """Callbacks that echo the record type and offer no hint."""

    async def _resolve(record_type: str | None, search_name: str | None) -> str | None:
        del search_name
        return record_type

    async def _hint(search_name: str, record_type: str | None) -> str | None:
        del search_name, record_type
        return None

    return ValidationCallbacks(
        resolve_record_type_for_search=_resolve, find_record_type_hint=_hint
    )


async def no_dependent_refresh(
    ctx: SearchContext, *, parameter_name: str, context_values: JSONObject
) -> list[WDKParameter]:
    del ctx, parameter_name, context_values
    return []
