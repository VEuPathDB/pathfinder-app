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

from strategist.domain.refusal import Check, RefusalKey
from strategist.platform.library_refusals import library_problems
from strategist.platform.refusals import ProblemsRefusal


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
        key = RefusalKey(check=Check.VALIDATION, search=search.search_name)
        raise ProblemsRefusal(library_problems(exc, key)) from exc
    canonical = resolved.model_copy(update={"params": validated.params})
    return canonical, validated.substituted
