"""``get_parameter_options`` answered from a sheet in hand: a query keeps the
entries whose value or label holds one of its terms."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from veupathdb_mcp.catalog import ParameterInfo, VocabLookup, VocabNarrowing

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
        folded = [term.casefold() for term in terms]
        kept = [
            option
            for option in info.vocabulary()
            if any(t in f"{option.value} {option.display}".casefold() for t in folded)
        ]
        return info.model_copy(
            update={
                "allowed_values": kept,
                "allowed_values_total": None,
                "vocab_lookup": VocabLookup(terms=list(terms)),
            }
        )

    monkeypatch.setattr(catalog_discovery, "read_parameter_options", _read)
