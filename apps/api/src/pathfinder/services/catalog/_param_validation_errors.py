"""The context a search-parameter validation failure reports."""

from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject

from pathfinder.domain.parameters.specs import ParamSpecNormalized
from pathfinder.domain.search import SearchContext
from pathfinder.integrations.veupathdb.discovery_service import DiscoveryService
from pathfinder.platform.errors import AppError, ValidationError

from .param_formatting import ParameterInfo, format_normalized_param_info

logger = get_logger(__name__)


class _InvalidDependentEntry(CamelModel):
    """One dependent parameter whose value is absent from its vocabulary."""

    name: str
    values: list[str]
    valid_options: list[JSONObject] | None = None


class _UnreadableSearchContext(CamelModel):
    """The record type whose catalog is offered when a search does not load."""

    record_type: str
    available_searches: list[str]
    record_type_hint: str | None = None


class _SpecErrorContext(CamelModel):
    """The search a validation error names, and its full parameter spec.

    Exactly one of the three middle fields carries the failure.
    """

    record_type: str
    search_name: str
    unknown: list[str] | None = None
    invalid_dependents: list[JSONObject] | None = None
    missing: list[str] | None = None
    parameters: list[JSONObject]


def _serialize(model: CamelModel) -> JSONObject:
    return model.model_dump(by_alias=True, mode="json", exclude_none=True)


def _spec_error(title: str, context: _SpecErrorContext) -> ValidationError:
    return ValidationError(title=title, errors=[{"context": _serialize(context)}])


def _serialized_specs(
    param_spec_map: dict[str, ParamSpecNormalized],
) -> list[JSONObject]:
    return [_serialize(info) for info in format_normalized_param_info(param_spec_map)]


def _valid_options(spec: ParameterInfo | None) -> list[JSONObject] | None:
    options = None if spec is None else spec.allowed_values
    return None if options is None else [_serialize(option) for option in options]


def unknown_params_error(
    *,
    record_type: str,
    search_name: str,
    param_spec_map: dict[str, ParamSpecNormalized],
    unknown: list[str],
) -> ValidationError:
    """The caller named parameters the search does not have."""
    return _spec_error(
        "Unknown parameters provided",
        _SpecErrorContext(
            record_type=record_type,
            search_name=search_name,
            unknown=unknown,
            parameters=_serialized_specs(param_spec_map),
        ),
    )


def missing_params_error(
    *,
    record_type: str,
    search_name: str,
    param_spec_map: dict[str, ParamSpecNormalized],
    missing: list[str],
) -> ValidationError:
    """The search requires parameters the caller left empty."""
    return _spec_error(
        f"Missing required parameters: {', '.join(missing)}",
        _SpecErrorContext(
            record_type=record_type,
            search_name=search_name,
            missing=missing,
            parameters=_serialized_specs(param_spec_map),
        ),
    )


def invalid_dependents_error(
    *,
    record_type: str,
    search_name: str,
    param_spec_map: dict[str, ParamSpecNormalized],
    violations: list[tuple[str, list[str]]],
) -> ValidationError:
    """A dependent value is absent from the vocabulary its parent produced."""
    details = ", ".join(f"{name}={bad}" for name, bad in violations)
    spec_by_name = {p.name: p for p in format_normalized_param_info(param_spec_map)}
    entries = [
        _InvalidDependentEntry(
            name=name,
            values=bad,
            valid_options=_valid_options(spec_by_name.get(name)),
        )
        for name, bad in violations
    ]
    return _spec_error(
        f"Invalid dependent-parameter values: {details}. "
        "Use the values from the validOptions list for each invalid "
        "dependent parameter: these are the post-refresh vocabulary "
        "for the parent's current value.",
        _SpecErrorContext(
            record_type=record_type,
            search_name=search_name,
            invalid_dependents=[_serialize(entry) for entry in entries],
            parameters=_serialized_specs(param_spec_map),
        ),
    )


def unknown_search_error(
    *, search_name: str, record_type: str | None, record_type_hint: str | None
) -> ValidationError:
    """No record type on the site publishes this search."""
    return ValidationError(
        title=f"Unknown or invalid search: {search_name}",
        detail="Search name not found in any record type.",
        errors=[
            {"context": {"recordType": record_type, "recordTypeHint": record_type_hint}}
        ],
    )


def unreadable_search_error(
    *,
    search_name: str,
    record_type: str,
    detail: str,
    available_searches: list[str],
    record_type_hint: str | None,
) -> ValidationError:
    """WDK refused the search definition, so the record type's catalog is offered."""
    context = _UnreadableSearchContext(
        record_type=record_type,
        available_searches=available_searches,
        record_type_hint=record_type_hint,
    )
    return ValidationError(
        title=f"Unknown or invalid search: {search_name}",
        detail=detail,
        errors=[{"context": context.model_dump(by_alias=True, mode="json")}],
    )


def wdk_rejection_error(
    *, detail: str, by_key: dict[str, list[str]]
) -> ValidationError:
    """WDK judged the caller's values while answering and refused them."""
    return ValidationError(
        title="Invalid parameter value",
        detail=detail or "WDK rejected these parameter values.",
        errors=[
            {"param": key, "messages": list(texts)} for key, texts in by_key.items()
        ],
    )


async def collect_available_search_names(
    discovery: DiscoveryService, site_id: str, resolved_record_type: str
) -> list[str]:
    """The search names a record type publishes."""
    searches = await discovery.get_searches(site_id, resolved_record_type)
    return [s.url_segment for s in searches]


async def find_search_record_type_hint(
    discovery: DiscoveryService, ctx: SearchContext
) -> str | None:
    """Search other record types to find where *search_name* actually lives."""
    try:
        record_types = await discovery.get_record_types(ctx.site_id)
        for rt in record_types:
            rt_name = rt.url_segment
            if not rt_name or rt_name == ctx.record_type:
                continue
            rt_searches = await discovery.get_searches(ctx.site_id, rt_name)
            for s in rt_searches:
                if ctx.search_name == s.url_segment:
                    return rt_name
    except AppError as hint_exc:
        logger.warning(
            "Record type hint resolution failed",
            search_name=ctx.search_name,
            error=str(hint_exc),
        )
    return None
