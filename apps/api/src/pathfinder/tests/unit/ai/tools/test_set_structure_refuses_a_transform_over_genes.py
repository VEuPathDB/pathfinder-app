"""``set_structure`` refuses a transform whose input returns a record class the
transform does not declare, before the tree is recorded."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone.frame_structure import (
    SetStructureResult,
    set_structure,
)
from pathfinder.domain.strategy.operational_spec import StructureNode
from pathfinder.services.strategies.record_classes import (
    record_class_names,
    search_record_classes,
)
from pathfinder.tests._support.organism_reads import serve_organism_reads
from pathfinder.tests._support.qa_recording import needs_suite_recordings
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context
from pathfinder.tests.unit.domain.strategy._n1_tree import (
    PF,
    blood_stage,
    drug_target,
    join,
    leaf,
    low_variation,
    no_human,
    three,
)


def _state() -> AgentToolState:
    state = AgentToolState()
    for criterion in (
        blood_stage("step_9ba9dec1"),
        low_variation("step_3a4dba81"),
        no_human("step_0ae0f092"),
        drug_target(),
    ):
        state.frame_set_criterion(criterion)
    return state


@pytest.mark.asyncio
@needs_suite_recordings
async def test_the_recorded_compounds_transform_takes_compounds() -> None:
    classes = await search_record_classes(
        "plasmodb", ["GenesByCompoundsTransform", "GenesByOrthologs", "Unlisted"]
    )

    assert {name: (c.returns, c.takes) for name, c in classes.items()} == {
        "GenesByCompoundsTransform": ("transcript", ("compound",)),
        "GenesByOrthologs": ("transcript", ("transcript",)),
    }
    assert await record_class_names("plasmodb") == {
        "transcript": "Genes",
        "compound": "Compounds",
    }


@pytest.mark.asyncio
@needs_suite_recordings
async def test_a_compounds_transform_over_a_copy_of_the_genes_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_organism_reads(monkeypatch, [PF])
    state = _state()
    existing = three("step_9ba9dec1", "step_3a4dba81", "step_0ae0f092")
    mapped = StructureNode(
        kind="transform",
        criterion_id="c_drug_target",
        inputs=[StructureNode(kind="copy", inputs=[existing.model_copy(deep=True)])],
    )

    with pytest.raises(ModelRetry) as exc:
        await set_structure(
            agent_run_context(agent_state=state),
            root=join(CombineOp.INTERSECT, existing, mapped),
        )

    assert str(exc.value) == (
        "The structure is refused: c_drug_target runs Transform to Genes "
        "(GenesByCompoundsTransform), which takes Compounds as its input step, "
        "and the subtree under it returns Genes. WDK runs a transform only on the "
        "record classes it declares, so this tree cannot run. Transform to Genes "
        "maps Compounds to Genes; it is not a filter on Genes. Drop c_drug_target, "
        "bind it to a search on Genes that states it, or ask the researcher. "
        "Nothing was recorded."
    )
    assert state.operational_spec_draft.structure is None


@pytest.mark.asyncio
async def test_the_genes_without_the_transform_are_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_organism_reads(monkeypatch, [PF])
    state = _state()
    state.frame_drop_criterion("c_drug_target", "not a filter on genes")
    root = join(
        CombineOp.INTERSECT,
        leaf("step_9ba9dec1"),
        leaf("step_3a4dba81"),
        leaf("step_0ae0f092"),
    )

    result = returned(
        await set_structure(agent_run_context(agent_state=state), root=root),
        SetStructureResult,
    )

    assert result.criteria_combined == 3
    assert state.operational_spec_draft.structure is not None
