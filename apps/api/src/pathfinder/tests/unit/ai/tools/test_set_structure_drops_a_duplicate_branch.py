"""``set_structure`` drops an INTERSECT input that repeats a sibling input,
removes its criteria and records them as met, never as a gap."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone.frame_structure import (
    SetStructureResult,
    StructureDrop,
    set_structure,
)
from pathfinder.tests._support.organism_reads import serve_organism_reads
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context, summary_of
from pathfinder.tests.unit.domain.strategy._n1_tree import (
    PF,
    blood_stage,
    join,
    leaf,
    low_variation,
    no_human,
    three,
)

ORIGINAL = ("step_9ba9dec1", "step_3a4dba81", "step_0ae0f092")
SECOND = ("step_e83414b3", "step_7764f323", "step_9f2e2b90")


def _state() -> AgentToolState:
    state = AgentToolState()
    for ids in (ORIGINAL, SECOND):
        for make, cid in zip((blood_stage, low_variation, no_human), ids, strict=True):
            state.frame_set_criterion(make(cid))
    state.frame_set_criterion(
        blood_stage("c_text").model_copy(
            update={"search_name": "GenesByText", "text": "drug target annotation"}
        )
    )
    return state


@pytest.mark.asyncio
async def test_the_second_copy_of_the_three_leaves_leaves_the_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_organism_reads(monkeypatch, [PF])
    state = _state()
    root = join(
        CombineOp.INTERSECT,
        join(CombineOp.INTERSECT, three(*ORIGINAL), leaf("c_text")),
        three(*SECOND),
    )

    result = await set_structure(agent_run_context(agent_state=state), root=root)

    shaped = returned(result, SetStructureResult)
    draft = state.operational_spec_draft
    assert draft.structure is not None
    assert draft.structure.root == join(
        CombineOp.INTERSECT, three(*ORIGINAL), leaf("c_text")
    )
    assert shaped.criteria_combined == 4
    assert [(d.criterion_id, d.met) for d in shaped.dropped] == [
        (cid, True) for cid in SECOND
    ]
    assert shaped.dropped[2] == StructureDrop(
        criterion_id="step_9f2e2b90",
        met=True,
        fate=(
            "step_9f2e2b90 ('P. falciparum 3D7 genes with no human equivalent') "
            "is dropped: it runs GenesByOrthologPattern with the values "
            "step_0ae0f092 runs beside it under INTERSECT, so step_0ae0f092 "
            "meets it."
        ),
    )
    assert sorted(c.id for c in draft.criteria) == sorted([*ORIGINAL, "c_text"])
    assert [(d.text, d.unexpressed) for d in draft.dropped] == [
        ("P. falciparum 3D7 genes expressed in the blood stage", False),
        (
            "P. falciparum 3D7 genes with variants per kb (CDS) <= 1 across isolates",
            False,
        ),
        ("P. falciparum 3D7 genes with no human equivalent", False),
    ]
    assert draft.unexpressed() == []
    assert summary_of(result).data["summary"] == (
        "Structure set: 4 searches; dropped step_e83414b3; dropped step_7764f323; "
        "dropped step_9f2e2b90"
    )
