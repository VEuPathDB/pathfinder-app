"""An edit over a bound analysis and a waiting one mints no step that carries an
analysis document: the bound one has its step, and the waiting one is the
export's to write."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import CombineOp
from veupathdb_mcp.catalog import EDA_ANALYSIS_SPEC_PARAM

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.domain.strategy.operations import AddLeafOp
from pathfinder.tests.unit.ai.lead._analysis_thread import WAITING, bare_thread
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    declared,
    joined,
    kept,
    leaf,
)
from pathfinder.tests.unit.ai.lead.test_an_analysis_criterion_across_edits import (
    _a_comparison_waits,
)


async def test_an_edit_beside_both_analysis_criteria_mints_only_the_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = bare_thread(monkeypatch)
    exported = await _a_comparison_waits(thread)
    written = len(thread.committed)

    def _draft(found: OperationalSpec) -> OperationalSpec:
        found.criteria.append(
            Criterion(
                id="c_kinase",
                text="protein kinases",
                search_name="GenesByText",
                resolved_params={"text_expression": StringValue(value="kinase")},
            )
        )
        found.structure = SpecStructure(
            root=joined(
                CombineOp.INTERSECT, leaf(exported), leaf(WAITING), leaf("c_kinase")
            )
        )
        return found

    thread.frames(_draft, declared=[*kept(exported), *declared("added", "c_kinase")])

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    minted = [op.step for op in thread.committed[written:] if isinstance(op, AddLeafOp)]
    assert [(step.id, step.search_name) for step in minted] == [
        ("c_kinase", "GenesByText")
    ]
    assert [EDA_ANALYSIS_SPEC_PARAM in step.parameters for step in minted] == [False]
