"""Filter reads a site answers with no range and no count."""

from __future__ import annotations

from collections.abc import Sequence

from veupathdb.domain.parameters import (
    FacetRange,
    FilterClause,
    FilterFacet,
    FilterValue,
)


class NoFilterReads:
    async def range(
        self,
        param: str,
        facet: FilterFacet,
        context: dict[str, str],
        others: Sequence[FilterClause],
    ) -> FacetRange | None:
        del param, facet, context, others
        return None

    async def selected(
        self, param: str, context: dict[str, str], value: FilterValue
    ) -> int | None:
        del param, context, value
        return None
