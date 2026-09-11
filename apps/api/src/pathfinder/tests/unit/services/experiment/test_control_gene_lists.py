"""The four control-test gene lists, including a control set that read no ids."""

from __future__ import annotations

import pytest
from veupathdb_mcp.controls import ControlSetData, ControlTargetData, ControlTestResult
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
    positive: ControlSetData | None = None, negative: ControlSetData | None = None
) -> ControlTestResult:
    return ControlTestResult(
        site_id="plasmodb",
        record_type="transcript",
        target=ControlTargetData(search_name="GenesByText"),
        positive=positive,
        negative=negative,
    )


async def test_the_four_lists_read_the_identifiers_each_control_set_carries() -> None:
    result = _result(
        positive=ControlSetData(
            controls_count=3,
            intersection_count=2,
            intersection_ids=["PF3D7_0100100", "PF3D7_0100200"],
            missing_ids_sample=["PF3D7_0100300"],
        ),
        negative=ControlSetData(
            controls_count=2,
            intersection_count=1,
            intersection_ids=["PF3D7_0200100"],
            missing_ids_sample=["PF3D7_0200200"],
        ),
    )

    tp, fn, fp, tn = await extract_and_hydrate_genes(
        site_id="plasmodb", result=result, negative_controls=None
    )

    assert [g.id for g in tp] == ["PF3D7_0100100", "PF3D7_0100200"]
    assert [g.id for g in fn] == ["PF3D7_0100300"]
    assert [g.id for g in fp] == ["PF3D7_0200100"]
    assert [g.id for g in tn] == ["PF3D7_0200200"]


async def test_a_control_set_that_read_no_ids_names_no_gene() -> None:
    """Over the answer-page limit a control set carries a count and no ids.

    One of the two negative controls was hit, so a list of both as true
    negatives would contradict the count the same result carries.
    """
    result = _result(
        negative=ControlSetData(controls_count=2, intersection_count=1),
    )

    _tp, _fn, fp, tn = await extract_and_hydrate_genes(
        site_id="plasmodb",
        result=result,
        negative_controls=["PF3D7_0200100", "PF3D7_0200200"],
    )

    assert [g.id for g in fp] == []
    assert [g.id for g in tn] == []


async def test_the_true_negatives_fall_back_to_the_controls_the_step_missed() -> None:
    result = _result(
        negative=ControlSetData(
            controls_count=2,
            intersection_count=1,
            intersection_ids=["PF3D7_0200100"],
        ),
    )

    _tp, _fn, _fp, tn = await extract_and_hydrate_genes(
        site_id="plasmodb",
        result=result,
        negative_controls=["PF3D7_0200100", "PF3D7_0200200"],
    )

    assert [g.id for g in tn] == ["PF3D7_0200200"]
