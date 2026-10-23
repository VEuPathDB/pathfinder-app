from __future__ import annotations

import pytest

from pathfinder.services.audit import confirm
from pathfinder.services.audit.checks import UnitFailure
from pathfinder.tests._support.orthomcl_gene_class import (
    NO_GENE_RECORDS,
    ORTHOMCL,
    held_record_types,
    orthomcl_gene_class,
)


async def test_a_gene_read_on_a_site_with_no_gene_records_is_a_named_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held_record_types(monkeypatch)

    with orthomcl_gene_class() as wire:
        placed = await confirm._organisms(ORTHOMCL, ["PF3D7_1133400"])

    assert placed == UnitFailure(
        status="failed",
        message=f"The site serves no gene records: {NO_GENE_RECORDS}",
    )
    assert (wire.gene_reads.call_count, wire.record_type_reads.call_count) == (1, 0)
