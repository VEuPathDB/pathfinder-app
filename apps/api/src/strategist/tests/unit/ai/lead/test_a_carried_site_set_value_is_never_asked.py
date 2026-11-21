from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, StringValue
from veupathdb.domain.strategy import StepValidation
from veupathdb.errors import ValidationError
from veupathdb.wdk import WDKSearchResponse

from strategist.ai.agents.frame_result_checks import hold_the_questions_to_the_draft
from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.lead import frame_dispatch
from strategist.ai.lead.deltas import FrameResult
from strategist.ai.lead.frame_dispatch import frame_work_order, run_frame
from strategist.domain.strategy.constraints import ConstraintKind
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from strategist.domain.strategy.questions import SlotQuestion
from strategist.services.strategies import sheet_params
from strategist.tests._support.recorded_searches import (
    client_search,
    serve_recorded,
    serve_recorded_record_types,
    suite_search,
)
from strategist.tests._support.run_context import run_context_for
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_TEXT = suite_search("search_genes_by_text")
_SNPS = client_search("search_genes_by_ngs_snps")


def _text() -> Criterion:
    return Criterion(
        id="c_text",
        text="kinases",
        search_name="GenesByText",
        resolved_params={
            "text_expression": BoundValue(
                value=StringValue(value="kinase"), source="stated"
            ),
            "document_type": BoundValue(
                value=StringValue(value="gene"), source="default"
            ),
        },
    )


def _snps() -> Criterion:
    return Criterion(
        id="c_snps",
        text="genes with SNPs",
        search_name="GenesByNgsSnps",
        resolved_params={
            "organismSinglePick": BoundValue(
                value=MultiPickValue(values=["Plasmodium falciparum 3D7"]),
                source="default",
            ),
            "eda_sample_table_suffix": BoundValue(
                value=SinglePickValue(value="s3be28bbe14_sample"), source="default"
            ),
        },
    )


def _ask(criterion_id: str, param_name: str) -> FrameResult:
    return FrameResult(
        disposition="needs_user",
        open_questions=[
            SlotQuestion(
                question=f"Which {param_name}?",
                dimension=ConstraintKind.UNTYPED,
                recommended_value="gene",
                criterion_id=criterion_id,
                param_name=param_name,
            )
        ],
    )


def _carried(monkeypatch: pytest.MonkeyPatch) -> Any:
    serve_recorded(monkeypatch, [_TEXT, _SNPS])
    serve_recorded_record_types(monkeypatch)
    deps = lead_deps(pipeline_state(user_prompt="kinases with SNPs"))
    deps.state.domain.operational_spec = OperationalSpec(
        goal="kinases with SNPs", criteria=[_text(), _snps()]
    )
    return deps


async def _frame_asks(monkeypatch: pytest.MonkeyPatch, asked: FrameResult) -> Any:
    deps = _carried(monkeypatch)

    async def _pass(**kwargs: Any) -> Any:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        return hold_the_questions_to_the_draft(run_context_for(agent_deps), asked)

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _pass)
    return await run_frame(
        deps=deps, parent_tool_call_id="t1", work_order=frame_work_order("go", deps)
    )


class _PassStartedError(Exception):
    pass


async def test_a_pass_starts_with_the_carried_searches_site_set_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _carried(monkeypatch)
    seen: dict[str, frozenset[str]] = {}

    async def _pass(**kwargs: Any) -> Any:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        seen.update(agent_deps.agent_state.site_set_read_this_pass)
        raise _PassStartedError

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _pass)

    with pytest.raises(_PassStartedError):
        await run_frame(
            deps=deps, parent_tool_call_id="t1", work_order=frame_work_order("go", deps)
        )

    assert seen == {
        "GenesByText": frozenset({"document_type"}),
        "GenesByNgsSnps": frozenset({"eda_sample_table_suffix", "WebServicesPath"}),
    }


async def test_a_question_on_a_carried_read_only_value_binds_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ModelRetry) as sent_back:
        await _frame_asks(monkeypatch, _ask("c_text", "document_type"))

    told = str(sent_back.value)
    assert "names c_text.document_type" in told
    assert "c_text: text_expression;" in told


async def test_a_question_on_a_carried_hidden_value_binds_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ModelRetry) as sent_back:
        await _frame_asks(monkeypatch, _ask("c_snps", "eda_sample_table_suffix"))

    told = str(sent_back.value)
    assert "names c_snps.eda_sample_table_suffix" in told
    assert "c_snps: organismSinglePick" in told


async def test_a_question_on_a_carried_value_the_researcher_sets_is_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[object] = []

    async def _run(**kwargs: Any) -> Any:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        held = hold_the_questions_to_the_draft(
            run_context_for(agent_deps), _ask("c_text", "text_expression")
        )
        seen.append(held)
        raise _PassStartedError

    deps = _carried(monkeypatch)
    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _run)

    with pytest.raises(_PassStartedError):
        await run_frame(
            deps=deps, parent_tool_call_id="t1", work_order=frame_work_order("go", deps)
        )

    assert seen == [_ask("c_text", "text_expression")]


async def test_a_carried_search_the_catalog_cannot_read_is_left_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _carried(monkeypatch)

    async def _details(
        ctx: SearchContext, **_kw: object
    ) -> tuple[WDKSearchResponse, str]:
        if ctx.search_name == "GenesByText":
            raise ValidationError(
                title="Search definition could not be read",
                detail=f"reading {ctx.search_name} failed",
            )
        validation = StepValidation(level="NONE", is_valid=False)
        return WDKSearchResponse(search_data=_SNPS, validation=validation), "transcript"

    monkeypatch.setattr(sheet_params, "fetch_search_details", _details)
    seen: dict[str, frozenset[str]] = {}

    async def _pass(**kwargs: Any) -> Any:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        seen.update(agent_deps.agent_state.site_set_read_this_pass)
        raise _PassStartedError

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _pass)

    with pytest.raises(_PassStartedError):
        await run_frame(
            deps=deps, parent_tool_call_id="t1", work_order=frame_work_order("go", deps)
        )

    assert seen == {
        "GenesByNgsSnps": frozenset({"eda_sample_table_suffix", "WebServicesPath"})
    }
