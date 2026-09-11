"""The catalog builders the spanning tests need, beside the tests that use them."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import pytest
from veupathdb.domain.parameters.values import ParamValue
from veupathdb.domain.search import SearchContext
from veupathdb.domain.strategy.validation import StepValidation
from veupathdb.json_types import JSONObject
from veupathdb.wdk.wdk_models import WDKSearch, WDKSearchResponse
from veupathdb.wdk.wdk_parameters import (
    WDKParameter,
)
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ResolvedSearch,
    ValidationCallbacks,
    param_validation,
)

type ParamsAt = Callable[[dict[str, str]], list[ParameterInfo]]
"""The parameters a search offers at one context, as a test answers them."""


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


class SearchDetailsResolver(Protocol):
    """The signature of the catalog read a test answers in place of WDK."""

    async def __call__(
        self,
        ctx: SearchContext,
        /,
        *,
        resolved_record_type: str,
        parameters: dict[str, ParamValue],
    ) -> ResolvedSearch: ...


def serve_search_details(
    monkeypatch: pytest.MonkeyPatch, resolver: SearchDetailsResolver
) -> None:
    """Answer the catalog's search-details read, and refresh no dependent parameter.

    This is the one place that reaches into the tool server's validation
    module, so a rename there is fixed here and nowhere else.
    """
    monkeypatch.setattr(param_validation, "resolve_search_details", resolver)
    monkeypatch.setattr(
        param_validation, "get_refreshed_dependent_params", no_dependent_refresh
    )
