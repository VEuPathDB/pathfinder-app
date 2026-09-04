"""Validation of search parameter values."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic import BaseModel, ConfigDict, Field

from pathfinder.domain.parameters.canonicalize import ParameterCanonicalizer
from pathfinder.domain.parameters.specs import (
    ParamSpecNormalized,
    fill_hidden_required_defaults,
    filled_hidden_defaults,
    find_dependent_value_violations,
    find_missing_required_params,
    topological_fill_order,
)
from pathfinder.domain.parameters.value_codec import to_decoded_map
from pathfinder.domain.parameters.values import ParamValue
from pathfinder.domain.search import SearchContext
from pathfinder.integrations.veupathdb.discovery_service import get_discovery_service
from pathfinder.integrations.veupathdb.factory import get_wdk_client
from pathfinder.integrations.veupathdb.wdk_models import (
    WDKSearchResponse,
    encode_wdk_params,
)
from pathfinder.platform.errors import AppError, ValidationError
from pathfinder.platform.tool_errors import ToolErrorPayload
from pathfinder.services.catalog.eda_backed import check_eda_parameters
from pathfinder.services.catalog.param_adapters import (
    adapt_param_from_wdk,
    adapt_param_specs_from_search,
)
from pathfinder.services.catalog.search_context import context_for_metadata_read
from pathfinder.services.catalog.wdk_substitution import substituted_params

from ._param_validation_errors import (
    collect_available_search_names,
    find_search_record_type_hint,
    invalid_dependents_error,
    missing_params_error,
    unknown_params_error,
    unknown_search_error,
    unreadable_search_error,
    wdk_rejection_error,
)
from .param_resolution import (
    _extract_param_names_from_response,
    _filter_context_values,
    expand_search_details_with_params,
    get_refreshed_dependent_params,
)

logger = get_logger(__name__)


class _ValidationErrorEntry(BaseModel):
    """Single error entry from WDK validation responses."""

    model_config = ConfigDict(extra="ignore")
    param: str | None = None
    path: str | None = None
    message: str | None = None
    detail: str | None = None


class ValidationErrors(CamelModel):
    """Structured validation errors by category."""

    general: list[str] = Field(default_factory=list)
    by_key: dict[str, list[str]] = Field(default_factory=dict)


class ValidationResult(CamelModel):
    """Single validation result with normalized values."""

    is_valid: bool
    normalized_context_values: JSONObject = Field(default_factory=dict)
    errors: ValidationErrors = Field(default_factory=ValidationErrors)


class ValidationResponse(CamelModel):
    """Top-level validation response wrapper."""

    validation: ValidationResult


@dataclass(frozen=True)
class ValidationCallbacks:
    """Caller-provided callbacks for parameter validation.

    Set the payload callback only when the caller must turn a validation error
    into a tool error payload.
    """

    resolve_record_type_for_search: Callable[
        [str | None, str | None], Awaitable[str | None]
    ]
    find_record_type_hint: Callable[[str, str | None], Awaitable[str | None]]
    validation_error_payload: Callable[[ValidationError], ToolErrorPayload] | None = (
        None
    )


async def validate_search_params(
    ctx: SearchContext,
    *,
    context_values: dict[str, ParamValue] | None,
) -> ValidationResponse:
    """Validate and canonicalize search parameters for the UI.

    The frontend consumes this result. It never interprets raw WDK payloads.
    """
    raw_context: dict[str, ParamValue] = context_values or {}
    response: WDKSearchResponse | None = None
    allowed: set[str] = set()

    try:
        response = await expand_search_details_with_params(ctx, raw_context)
        allowed = _extract_param_names_from_response(response)
    except AppError as exc:
        return ValidationResponse(
            validation=ValidationResult(
                is_valid=False,
                errors=ValidationErrors(
                    general=[f"Failed to load search metadata: {exc}"]
                ),
            )
        )

    filtered_context = _filter_context_values(raw_context, allowed)
    spec_map = adapt_param_specs_from_search(response.search_data)

    try:
        canonicalizer = ParameterCanonicalizer(spec_map)
        normalized_context = canonicalizer.canonicalize(filtered_context)
    except ValidationError as exc:
        by_key: dict[str, list[str]] = {}
        general: list[str] = []
        for err_raw in exc.errors or []:
            if not isinstance(err_raw, dict):
                continue
            entry = _ValidationErrorEntry.model_validate(err_raw)
            param_name = entry.param or entry.path
            message = entry.message or entry.detail or exc.detail or exc.title
            if param_name:
                by_key.setdefault(param_name, []).append(message)
            else:
                general.append(str(message))
        if not general:
            general = [exc.detail or exc.title]
        return ValidationResponse(
            validation=ValidationResult(
                is_valid=False,
                errors=ValidationErrors(general=general, by_key=by_key),
            )
        )

    decoded_normalized = to_decoded_map(normalized_context)

    # Required checks using raw WDK specs (keeps semantics aligned with WDK).
    missing = find_missing_required_params(spec_map, decoded_normalized)

    if missing:
        by_key = {name: ["Required"] for name in missing}
        return ValidationResponse(
            validation=ValidationResult(
                is_valid=False,
                normalized_context_values=decoded_normalized,
                errors=ValidationErrors(
                    general=[f"Missing required parameters: {', '.join(missing)}"],
                    by_key=by_key,
                ),
            )
        )

    return ValidationResponse(
        validation=ValidationResult(
            is_valid=True,
            normalized_context_values=decoded_normalized,
        )
    )


@dataclass(frozen=True)
class ResolvedSearch:
    """A search definition, and whether WDK built it from the caller's values."""

    response: WDKSearchResponse
    values_were_read: bool


async def _resolve_search_details(
    ctx: SearchContext,
    *,
    resolved_record_type: str,
    parameters: dict[str, ParamValue],
) -> ResolvedSearch:
    """Fetch search details with contextual params, or fall back to static specs.

    The context keeps the original identifiers for error hints. Raises a
    validation error with search hints when WDK does not know the search.
    """
    discovery = get_discovery_service()
    try:
        wdk_client = get_wdk_client(ctx.site_id)
        resolved_ctx = SearchContext(ctx.site_id, resolved_record_type, ctx.search_name)
        published = await discovery.get_search_details(resolved_ctx, expand_params=True)
        context = context_for_metadata_read(
            encode_wdk_params(parameters), published.search_data.parameters
        )
        try:
            return ResolvedSearch(
                response=await wdk_client.get_search_details_with_params(
                    resolved_record_type,
                    ctx.search_name,
                    context=context,
                    expand_params=True,
                ),
                values_were_read=True,
            )
        except AppError as exc:
            logger.warning(
                "Contextual param fetch failed, falling back to non-contextual specs",
                record_type=resolved_record_type,
                search_name=ctx.search_name,
                error=str(exc),
            )
            return ResolvedSearch(response=published, values_were_read=False)
    except AppError as exc:
        hint_record_type = await find_search_record_type_hint(discovery, ctx)
        available = await collect_available_search_names(
            discovery, ctx.site_id, resolved_record_type
        )
        raise unreadable_search_error(
            search_name=ctx.search_name,
            record_type=resolved_record_type,
            detail=str(exc),
            available_searches=available,
            record_type_hint=hint_record_type,
        ) from exc


class ValidatedParams(CamelModel):
    """Canonical values, the record class WDK lists the search under, and the
    names WDK supplied rather than accepted."""

    params: dict[str, ParamValue] = Field(default_factory=dict)
    record_class: str | None = None
    substituted: list[str] = Field(default_factory=list)


async def validate_parameters(
    ctx: SearchContext,
    *,
    parameters: dict[str, ParamValue],
    callbacks: ValidationCallbacks,
) -> ValidatedParams:
    resolved_record_type = await callbacks.resolve_record_type_for_search(
        ctx.record_type, ctx.search_name
    )
    if resolved_record_type is None:
        record_type_hint = await callbacks.find_record_type_hint(
            ctx.search_name, ctx.record_type
        )
        raise unknown_search_error(
            search_name=ctx.search_name,
            record_type=ctx.record_type,
            record_type_hint=record_type_hint,
        )

    resolved = await _resolve_search_details(
        ctx,
        resolved_record_type=resolved_record_type,
        parameters=parameters,
    )
    response = resolved.response
    check_eda_parameters(response.search_data, encode_wdk_params(parameters))

    param_spec_map = adapt_param_specs_from_search(response.search_data)
    canonicalizer = ParameterCanonicalizer(param_spec_map)
    canonical: dict[str, ParamValue] = canonicalizer.canonicalize(parameters)

    # A tree param counts only its leaves, so a branch selection scores zero
    # until it is expanded. WDK must judge what will be sent, not what arrived.
    if encode_wdk_params(canonical) != encode_wdk_params(parameters):
        resolved = await _resolve_search_details(
            ctx,
            resolved_record_type=resolved_record_type,
            parameters=canonical,
        )
        response = resolved.response
        param_spec_map = adapt_param_specs_from_search(response.search_data)

    # WDK validated these values while answering. Its verdict is authoritative,
    # so it is read before the local checks rather than recomputed after them.
    # A definition built without the caller's values judged a different shape.
    if resolved.values_were_read and response.validation.rejects():
        raise wdk_rejection_error(
            detail="; ".join(response.validation.messages()),
            by_key=(
                response.validation.errors.by_key if response.validation.errors else {}
            ),
        )

    refreshed_ctx = SearchContext(
        site_id=ctx.site_id,
        record_type=resolved_record_type,
        search_name=ctx.search_name,
    )
    # The refresh below skips a parent whose value is empty, so hidden required
    # parents must get their defaults first.
    canonical = fill_hidden_required_defaults(param_spec_map, canonical)
    param_spec_map = await _refresh_dependent_vocabularies(
        ctx=refreshed_ctx,
        param_spec_map=param_spec_map,
        canonical_values=canonical,
    )
    canonicalizer = ParameterCanonicalizer(param_spec_map)
    caller_canonical = canonicalizer.canonicalize(parameters)
    canonical = fill_hidden_required_defaults(param_spec_map, caller_canonical)
    param_names = _extract_param_names_from_response(response)
    extra_params = [key for key in canonical if key not in param_names]
    if extra_params:
        raise unknown_params_error(
            record_type=resolved_record_type,
            search_name=ctx.search_name,
            param_spec_map=param_spec_map,
            unknown=extra_params,
        )
    decoded_canonical = to_decoded_map(canonical)
    invalid_dependents = find_dependent_value_violations(
        param_spec_map,
        decoded_canonical,
    )
    if invalid_dependents:
        raise invalid_dependents_error(
            record_type=resolved_record_type,
            search_name=ctx.search_name,
            param_spec_map=param_spec_map,
            violations=invalid_dependents,
        )

    missing = find_missing_required_params(param_spec_map, to_decoded_map(canonical))

    if missing:
        raise missing_params_error(
            record_type=resolved_record_type,
            search_name=ctx.search_name,
            param_spec_map=param_spec_map,
            missing=missing,
        )
    echoed = {
        spec.name: spec.initial_display_value
        for spec in response.search_data.parameters or []
        if spec.initial_display_value is not None
    }
    # A hidden parameter PathFinder filled is a value nobody chose, so it is
    # reported alongside the ones WDK substituted. Both are read against the
    # caller's own canonical values, which is what WDK was asked to judge.
    substituted = sorted(
        set(
            substituted_params(
                sent=caller_canonical,
                echoed=echoed,
                specs=param_spec_map,
                values_were_read=resolved.values_were_read,
            )
        )
        | set(filled_hidden_defaults(param_spec_map, caller_canonical))
    )
    return ValidatedParams(
        params=canonical,
        record_class=resolved_record_type,
        substituted=substituted,
    )


async def _refresh_dependent_vocabularies(
    *,
    ctx: SearchContext,
    param_spec_map: dict[str, ParamSpecNormalized],
    canonical_values: dict[str, ParamValue],
) -> dict[str, ParamSpecNormalized]:
    """Refresh each dependent vocabulary against its parent's canonical value.

    A parent with an empty value keeps the static child vocabulary. A failed
    refresh also keeps the static vocabulary.
    """
    next_specs = dict(param_spec_map)
    fill_order = topological_fill_order(next_specs)
    decoded_values = to_decoded_map(canonical_values)
    for parent_name in fill_order:
        parent = next_specs.get(parent_name)
        if parent is None or not parent.dependent_params:
            continue
        parent_value = decoded_values.get(parent_name)
        if parent_value in (None, "", [], {}):
            continue
        try:
            refreshed = await get_refreshed_dependent_params(
                ctx,
                parameter_name=parent_name,
                context_values=canonical_values,
            )
        except AppError as exc:
            logger.warning(
                "refreshed-dependent-params failed; falling back to static vocab",
                parent=parent_name,
                search=ctx.search_name,
                error=str(exc),
            )
            continue
        for refreshed_param in refreshed:
            if refreshed_param.name in parent.dependent_params:
                next_specs[refreshed_param.name] = adapt_param_from_wdk(refreshed_param)
    return next_specs
