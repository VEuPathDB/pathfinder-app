"""FRAME reads an exported analysis as bound: it keeps it and places it."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.agents.strategy_instructions import pinned_frame_workspace
from pathfinder.ai.tools.standalone.frame_drop import drop_criterion
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.ai.tools.standalone.frame_structure import set_structure
from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    genes_by_text,
    serve_params,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec_sheet import (
    serve_genes_by_text_definition,
)
from pathfinder.tests.unit.domain.strategy._analysis import (
    DATASET,
    EXPORTED,
    WORDS,
    analysed,
    pending,
)

_WAITING = "c_24h_vs_36_up"


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _state() -> AgentToolState:
    """The draft an edit starts from: the export, and a comparison waiting."""
    return AgentToolState(
        operational_spec_draft=OperationalSpec(
            goal="24 h over 18 h and 36 h",
            criteria=[analysed(), pending(_WAITING)],
            structure=SpecStructure(
                root=StructureNode(
                    kind="combine",
                    operator=CombineOp.INTERSECT,
                    inputs=[_leaf(EXPORTED), _leaf(_WAITING)],
                )
            ),
        )
    )


async def test_a_bound_analysis_is_never_re_bound_and_nothing_is_dropped() -> None:
    state = _state()
    before = state.operational_spec_draft.model_copy(deep=True)

    with pytest.raises(ModelRetry) as excinfo:
        await set_criterion(
            frame_ctx(state),
            criterion_id=EXPORTED,
            text="fold change 24 h over 18 h",
            search_name="GenesByRNASeqvect_AGAMP4_Rund_rnaSeq_RSRCfoldChange",
        )

    assert "bound to the analysis workflow" in str(excinfo.value)
    assert "delete_step" in str(excinfo.value)
    assert state.operational_spec_draft == before


async def test_a_waiting_comparison_is_never_bound_to_another_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the export binds a criterion that waits for its analysis."""
    serve_genes_by_text_definition(monkeypatch)
    serve_params(monkeypatch, genes_by_text)
    state = _state()
    before = state.operational_spec_draft.model_copy(deep=True)

    with pytest.raises(ModelRetry) as excinfo:
        await set_criterion(
            frame_ctx(state),
            criterion_id=_WAITING,
            text="fold change 24 h over 36 h",
            search_name="GenesByText",
        )

    assert f'create_eda_step(criterion_id="{_WAITING}")' in str(excinfo.value)
    assert "bind no other search" in str(excinfo.value)
    assert (state.operational_spec_draft, state.open_sheets) == (before, {})


async def test_a_waiting_comparison_never_starts_from_a_saved_strategy() -> None:
    state = _state()
    before = state.operational_spec_draft.model_copy(deep=True)

    with pytest.raises(ModelRetry) as excinfo:
        await set_criterion(
            frame_ctx(state),
            criterion_id=_WAITING,
            text="24 h over 36 h",
            saved_strategy="DESeq 24 h vs 36 h",
        )

    assert f'create_eda_step(criterion_id="{_WAITING}")' in str(excinfo.value)
    assert state.operational_spec_draft == before


def test_a_bound_analysis_is_never_dropped_by_framing() -> None:
    state = _state()
    before = state.operational_spec_draft.model_copy(deep=True)

    with pytest.raises(ModelRetry) as excinfo:
        drop_criterion(frame_ctx(state), criterion_id=EXPORTED, reason="restated")

    assert "the Lead removes it with delete_step" in str(excinfo.value)
    assert state.operational_spec_draft == before


def test_a_waiting_comparison_may_still_be_dropped() -> None:
    state = _state()

    drop_criterion(frame_ctx(state), criterion_id=_WAITING, reason="not asked")

    assert [c.id for c in state.operational_spec_draft.criteria] == [EXPORTED]


@pytest.mark.parametrize("left_out", [EXPORTED, _WAITING])
async def test_a_tree_that_leaves_out_an_analysis_is_refused(left_out: str) -> None:
    state = _state()
    before = state.operational_spec_draft.structure
    kept = _WAITING if left_out == EXPORTED else EXPORTED

    with pytest.raises(ModelRetry) as excinfo:
        await set_structure(frame_ctx(state), root=_leaf(kept))

    assert f"leaves out ['{left_out}']" in str(excinfo.value)
    assert state.operational_spec_draft.structure == before


def test_the_workspace_states_the_analysis_by_its_words_and_no_document() -> None:
    workspace = pinned_frame_workspace(frame_ctx(_state()))

    assert workspace is not None
    assert (
        f"- [{EXPORTED}] {WORDS} -> analysis workflow, BOUND: keep it; do not "
        f"re-bind, drop, or restate this comparison with another search"
    ) in workspace
    assert (
        f"- [{_WAITING}] genes higher at 24 h than at 36 h, significant -> "
        f"analysis workflow on dataset {DATASET}, WAITING: keep it in the structure"
    ) in workspace
    assert "eda_analysis_spec" not in workspace
