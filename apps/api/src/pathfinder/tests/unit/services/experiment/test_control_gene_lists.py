"""The four control-test gene lists read the ids each control set filed."""

from __future__ import annotations

import pytest
from veupathdb_mcp.controls import (
    ControlTargetData,
    ControlTestResult,
    NegativeControls,
    PositiveControls,
)
from veupathdb_mcp.gene_lookup import GeneResolveResult

from pathfinder.services.experiment import helpers
from pathfinder.services.experiment.helpers import extract_and_hydrate_genes


@pytest.fixture(autouse=True)
def _no_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _resolve(site_id: str, gene_ids: list[str]) -> GeneResolveResult:
        del site_id, gene_ids
        return GeneResolveResult(records=[], total_count=0)

    monkeypatch.setattr(helpers, "resolve_gene_ids", _resolve)


def _result(
    positive: PositiveControls | None = None, negative: NegativeControls | None = None
) -> ControlTestResult:
    return ControlTestResult(
        site_id="plasmodb",
        record_type="transcript",
        target=ControlTargetData(search_name="GenesByText"),
        positive=positive,
        negative=negative,
    )


async def test_the_four_lists_read_the_identifiers_each_control_set_filed() -> None:
    result = _result(
        positive=PositiveControls(
            recovered_ids=["PF3D7_0100100", "PF3D7_0100200"],
            missed_ids=["PF3D7_0100300"],
        ),
        negative=NegativeControls(
            admitted_ids=["PF3D7_0200100"], excluded_ids=["PF3D7_0200200"]
        ),
    )

    tp, fn, fp, tn = await extract_and_hydrate_genes(site_id="plasmodb", result=result)

    assert [g.id for g in tp] == ["PF3D7_0100100", "PF3D7_0100200"]
    assert [g.id for g in fn] == ["PF3D7_0100300"]
    assert [g.id for g in fp] == ["PF3D7_0200100"]
    assert [g.id for g in tn] == ["PF3D7_0200200"]


async def test_a_kind_the_test_was_not_given_names_no_gene() -> None:
    result = _result(
        positive=PositiveControls(recovered_ids=["PF3D7_0100100"], missed_ids=[]),
    )

    tp, fn, fp, tn = await extract_and_hydrate_genes(site_id="plasmodb", result=result)

    assert [g.id for g in tp] == ["PF3D7_0100100"]
    assert fn == []
    assert fp == []
    assert tn == []
