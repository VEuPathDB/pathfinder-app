"""The binding WDK renders for one set_criterion call."""

from __future__ import annotations

from veupathdb.domain import SearchContext
from veupathdb.errors import ValidationError
from veupathdb_mcp.catalog import (
    ResolveContext,
    ResolvedParams,
    make_validation_callbacks,
    validate_parameters,
)

from strategist.domain.refusal import RefusalKey
from strategist.platform.refusals import library_problems, refusal_of


async def canonical_binding(
    search: SearchContext, resolved: ResolvedParams, about: ResolveContext
) -> tuple[ResolvedParams, list[str]]:
    """The binding WDK renders, and the values WDK supplied rather than accepted.
    A tree parameter scores its leaves alone, so these are the values a count
    and a build both send."""
    try:
        validated = await validate_parameters(
            search,
            stated=dict(resolved.params),
            callbacks=make_validation_callbacks(search.site_id),
            about=about,
        )
    except ValidationError as exc:
        key = RefusalKey(check="validation", search=search.search_name)
        raise refusal_of(library_problems(exc, key)) from exc
    canonical = resolved.model_copy(update={"params": validated.params})
    return canonical, validated.substituted
