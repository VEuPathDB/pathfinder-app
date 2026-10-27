from __future__ import annotations

from collections.abc import Mapping

import pytest
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.domain.strategy.operational_spec import BoundValue, ValueSource
from pathfinder.services.strategies.measurements import (
    MeasuredBinding,
    TurnCounts,
    measure_binding,
)
from pathfinder.tests._support.recorded_counts import serve_counts, wire
from pathfinder.tests._support.recorded_searches import suite_search

_SHEET = format_param_info_typed(
    list(
        suite_search("search_genes_by_interpro_domain_under_pf3d7_pfam").parameters
        or []
    )
)
_SENT: dict[str, tuple[ParamValue, ValueSource]] = {
    "organism": (MultiPickValue(values=["Plasmodium falciparum 3D7"]), "stated"),
    "domain_database": (SinglePickValue(value="Pfam"), "default"),
    "domain_typeahead": (MultiPickValue(values=["PF00069"]), "chosen"),
    "domain_accession": (StringValue(value="N/A"), "default"),
}


async def test_a_parent_whose_child_pick_is_bound_is_never_counted_at_another_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    databases: list[str] = []

    def _count(_search: str, params: Mapping[str, ParamValue]) -> int:
        databases.append(wire(params, "domain_database"))
        return 81

    serve_counts(monkeypatch, _count)
    params = {name: value for name, (value, _) in _SENT.items()}

    measured = await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="plasmodb",
            record_type="transcript",
            search_name="GenesByInterproDomain",
            params=params,
            count=81,
            organism_param="organism",
        ),
        values={
            name: BoundValue(value=value, source=source)
            for name, (value, source) in _SENT.items()
        },
        infos=_SHEET,
    )

    assert set(databases) <= {"Pfam"}
    assert "domain_database" not in {m.param for m in measured}
