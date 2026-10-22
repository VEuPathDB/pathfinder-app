from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone.frame_structure import set_structure
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests._support.record_classes import list_searches_under
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    bind,
    frame_ctx,
    param_info,
    serve_search,
)

_PATTERN = "GroupsByPhyleticPattern"
_EXPRESSION = "pfal+pber+pviv>=2T AND tgon=0T"


def _sheet(context: dict[str, str]) -> list[ParameterInfo]:
    del context
    return [param_info("phyletic_expression", display_name="Expression")]


@pytest.fixture(autouse=True)
def _pattern_search(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_search(monkeypatch, _sheet, url_segment=_PATTERN, display_name="Phyletic")
    list_searches_under(monkeypatch, "group", {_PATTERN})


async def test_a_bound_pattern_search_frames_the_spec_on_the_group_class() -> None:
    state = AgentToolState()
    await bind(
        state,
        _PATTERN,
        {"phyletic_expression": _EXPRESSION},
        criterion_id="c_groups",
        text="ortholog groups in most Plasmodium genomes and no Toxoplasma genome",
    )

    await set_structure(
        frame_ctx(state), root=StructureNode(kind="leaf", criterion_id="c_groups")
    )

    draft = state.operational_spec_draft
    assert [c.record_class for c in draft.criteria] == ["group"]
    assert draft.record_type == "group"


def _criterion(criterion_id: str, search_name: str, record_class: str) -> Criterion:
    return Criterion(
        id=criterion_id,
        text=criterion_id,
        search_name=search_name,
        record_class=record_class,
    )


def _transform() -> SpecStructure:
    return SpecStructure(
        root=StructureNode(
            kind="transform",
            criterion_id="c_groups",
            inputs=[StructureNode(kind="leaf", criterion_id="c_proteins")],
        )
    )


def _framed(*criteria: Criterion) -> AgentToolState:
    state = AgentToolState()
    for criterion in criteria:
        state.frame_set_criterion(criterion)
    return state


def test_a_transform_at_the_root_frames_the_spec_on_the_class_it_returns() -> None:
    state = _framed(
        _criterion("c_proteins", "ByIdList", "sequence"),
        _criterion("c_groups", "GroupsFromSequences", "group"),
    )

    state.frame_set_structure(_transform())

    assert state.operational_spec_draft.record_type == "group"


def test_a_combine_frames_the_spec_on_the_class_its_inputs_return() -> None:
    state = _framed(
        _criterion("c_ids", "ByIdList", "sequence"),
        _criterion("c_pfal", "ByTaxonomy", "sequence"),
    )

    state.frame_set_structure(
        SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="c_ids"),
                    StructureNode(kind="leaf", criterion_id="c_pfal"),
                ],
            )
        )
    )

    assert state.operational_spec_draft.record_type == "sequence"


def test_a_removed_transform_frames_the_spec_on_its_input_again() -> None:
    state = _framed(
        _criterion("c_proteins", "ByIdList", "sequence"),
        _criterion("c_groups", "GroupsFromSequences", "group"),
    )
    state.frame_set_structure(_transform())

    state.drop_criteria_for_steps(["c_groups"])

    assert state.operational_spec_draft.record_type == "sequence"


def test_a_dropped_root_criterion_frames_the_spec_on_what_is_left() -> None:
    state = _framed(
        _criterion("c_proteins", "ByIdList", "sequence"),
        _criterion("c_groups", "GroupsFromSequences", "group"),
    )

    state.frame_drop_criterion("c_groups", "no search states it")

    assert state.operational_spec_draft.record_type == "sequence"
