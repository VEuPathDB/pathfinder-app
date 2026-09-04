"""Site-bound callbacks that parameter validation needs."""

from __future__ import annotations

from collections.abc import Callable

from pathfinder.platform.errors import ValidationError
from pathfinder.platform.tool_errors import ToolErrorPayload
from pathfinder.services.catalog.param_validation import ValidationCallbacks
from pathfinder.services.catalog.record_type_resolution import (
    find_record_type_for_search,
    find_record_type_hint,
)


def make_validation_callbacks(
    site_id: str,
    *,
    error_payload: Callable[[ValidationError], ToolErrorPayload] | None = None,
) -> ValidationCallbacks:
    async def _resolve(
        record_type: str | None,
        search_name: str | None,
    ) -> str | None:
        return await find_record_type_for_search(
            site_id,
            record_type,
            search_name,
            require_match=True,
            allow_fallback=True,
        )

    async def _hint(search_name: str, exclude: str | None = None) -> str | None:
        return await find_record_type_hint(site_id, search_name, exclude)

    return ValidationCallbacks(
        resolve_record_type_for_search=_resolve,
        find_record_type_hint=_hint,
        validation_error_payload=error_payload,
    )
