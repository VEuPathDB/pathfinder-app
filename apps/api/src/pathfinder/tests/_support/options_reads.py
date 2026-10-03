"""``get_parameter_options`` answered from a sheet in hand: a query keeps the
entries whose value or label holds one of its terms, each counted under the
first term that holds it."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from veupathdb.domain.parameters import VocabOption
from veupathdb_mcp.catalog import (
    ParameterInfo,
    PhrasingMatch,
    VocabLookup,
    VocabNarrowing,
)

from pathfinder.ai.tools.standalone import catalog_discovery


def serve_options_reads(
    monkeypatch: pytest.MonkeyPatch, sheet_of: Callable[[str], list[ParameterInfo]]
) -> None:
    """Answer each options read from ``sheet_of(search_name)``."""

    async def _read(
        _site_id: str,
        search_name: str,
        parameter_id: str,
        *,
        record_type: str | None = None,
        context_values: object = None,
        narrowing: VocabNarrowing | None = None,
    ) -> ParameterInfo:
        del record_type, context_values
        info = next(i for i in sheet_of(search_name) if i.name == parameter_id)
        terms = narrowing.terms if narrowing else ()
        if not terms:
            return info
        claimed: dict[str, list[VocabOption]] = {term: [] for term in terms}
        for option in info.vocabulary():
            label = f"{option.value} {option.display}".casefold()
            first = next((t for t in terms if t.casefold() in label), None)
            if first is not None:
                claimed[first].append(option)
        lookup = VocabLookup(
            terms=list(terms),
            matches=[
                PhrasingMatch(
                    term=term,
                    phrasing=term.casefold(),
                    reach="phrase",
                    values=[option.value for option in options],
                )
                for term, options in claimed.items()
                if options
            ],
        )
        return info.model_copy(
            update={
                "allowed_values": [o for options in claimed.values() for o in options],
                "allowed_values_total": None,
                "vocab_lookup": lookup,
            }
        )

    monkeypatch.setattr(catalog_discovery, "read_parameter_options", _read)
