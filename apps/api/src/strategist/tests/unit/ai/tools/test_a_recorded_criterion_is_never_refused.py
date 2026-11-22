from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tool_manager import ToolManager
from veupathdb.domain.parameters import StringValue
from veupathdb_mcp.catalog import EDA_DATASET_ID_PARAM

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.toolsets.frame import build_toolset
from strategist.domain.refusal import RefusalKey
from strategist.domain.strategy.operational_spec import Criterion
from strategist.platform.refusals import ProblemsRefusal
from strategist.tests._support.bound_values import bound
from strategist.tests._support.catalog_reads import listing
from strategist.tests.unit.ai.tools.test_frame_spec import bind, frame_ctx
from strategist.tests.unit.ai.tools.test_frame_spec_eda import (
    _DATASET_ID,
    _MUTAGENESIS_SEARCH,
    _serve_the_eda_search,
)

_CUT_TRY_STEPS = (
    ("c_essential_tg_litic",),
    (
        "c_essential_tg_acute",
        "c_essential_pkno_h",
        "c_essential_pkno_a1h1",
        "c_essential_pber",
    ),
)


@pytest.fixture
def _eda_search(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve_the_eda_search(monkeypatch, default=_DATASET_ID)


@pytest.mark.usefixtures("_eda_search")
async def test_an_eda_backed_search_returns_the_criterion_waiting() -> None:
    state = AgentToolState()

    result = await bind(
        state,
        _MUTAGENESIS_SEARCH,
        {EDA_DATASET_ID_PARAM: _DATASET_ID},
        criterion_id="c_essential",
        text="essential in blood stages",
    )

    assert result.waits_for_analysis_on == _DATASET_ID
    assert result.criterion_id == "c_essential"
    assert result.search_name == _MUTAGENESIS_SEARCH
    assert state.operational_spec_draft.criteria == [
        Criterion(
            id="c_essential",
            text="essential in blood stages",
            needs_analysis_on=_DATASET_ID,
        )
    ]


@pytest.mark.usefixtures("_eda_search")
async def test_five_waiting_criteria_in_one_pass_spend_nothing() -> None:
    state = AgentToolState()
    state.record_catalog_read(listing([_MUTAGENESIS_SEARCH]))
    ctx = frame_ctx(state)
    manager = ToolManager(toolset=build_toolset())

    for number, criteria in enumerate(_CUT_TRY_STEPS, start=1):
        ctx = replace(ctx, run_step=number)
        manager = await manager.for_run_step(ctx)
        for criterion_id in criteria:
            await manager.handle_call(
                ToolCallPart(
                    tool_name="set_criterion",
                    args={
                        "criterion_id": criterion_id,
                        "text": f"essential ({criterion_id})",
                        "search_name": _MUTAGENESIS_SEARCH,
                        "role": "filter",
                    },
                    tool_call_id=f"call_{criterion_id}",
                )
            )
    manager = await manager.for_run_step(replace(ctx, run_step=len(_CUT_TRY_STEPS) + 1))

    assert manager.ctx is not None
    assert manager.ctx.retries.get("set_criterion", 0) == 0
    assert ctx.deps.refusal_book.ledger.uses == ()
    assert [c.needs_analysis_on for c in state.operational_spec_draft.criteria] == [
        _DATASET_ID
    ] * 5


async def test_a_search_that_names_no_dataset_is_refused_and_records_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve_the_eda_search(monkeypatch, default=None)
    state = AgentToolState()

    with pytest.raises(ProblemsRefusal) as refused:
        await bind(state, _MUTAGENESIS_SEARCH, {}, criterion_id="c_essential")

    assert refused.value.problems.keys() == (
        RefusalKey(
            check="eda_wait", criterion="c_essential", search=_MUTAGENESIS_SEARCH
        ),
    )
    assert f'params={{"{EDA_DATASET_ID_PARAM}": ' in str(refused.value)
    assert state.operational_spec_draft.criteria == []


@pytest.mark.usefixtures("_eda_search")
async def test_an_id_bound_to_another_search_is_refused_and_kept() -> None:
    held = Criterion(
        id="c_ring",
        text="top 20 percent expressed in Ring",
        search_name="GenesByRNASeqpfal3D7_Su_seven_stages_rnaSeq_RSRCPercentile",
        resolved_params=bound({"samples": StringValue(value="Ring")}),
        result_count=1102,
    )
    state = AgentToolState()
    state.frame_set_criterion(held)

    with pytest.raises(ProblemsRefusal) as refused:
        await bind(
            state,
            _MUTAGENESIS_SEARCH,
            {EDA_DATASET_ID_PARAM: _DATASET_ID},
            criterion_id="c_ring",
        )

    assert "Name a new criterion id" in str(refused.value)
    assert state.operational_spec_draft.criteria == [held]
