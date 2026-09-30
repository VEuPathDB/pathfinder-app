"""A bind the site refuses to count records nothing; one it did not count in
time stays bound with no count."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import ParamValue
from veupathdb.errors import WDKError

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone import _frame_count
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    Proposals,
    bind,
    genes_by_text,
    serve_search,
)

_KINASE: Proposals = {
    "text_expression": "kinase",
    "text_search_organism": ["Plasmodium"],
    "document_type": None,
    "text_fields": None,
}


def _serve_count(monkeypatch: pytest.MonkeyPatch, count: int | None) -> None:
    async def _count(
        site_id: str,
        record_type: str,
        search_name: str,
        params: Mapping[str, ParamValue],
    ) -> int | None:
        return count

    monkeypatch.setattr(_frame_count, "count_bound_criterion", _count)


def _refuse_count(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    async def _count(
        site_id: str,
        record_type: str,
        search_name: str,
        params: Mapping[str, ParamValue],
    ) -> int | None:
        detail = "Server error '500 500'"
        raise WDKError(detail, status=status)

    monkeypatch.setattr(_frame_count, "count_bound_criterion", _count)


@pytest.mark.asyncio
async def test_a_count_the_site_refuses_leaves_no_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    _refuse_count(monkeypatch, 500)
    state = AgentToolState()

    with pytest.raises(ModelRetry) as refused:
        await bind(state, "GenesByText", _KINASE)

    assert state.operational_spec_draft.criteria == []
    assert "HTTP 500" in str(refused.value)
    assert "GenesByText" in str(refused.value)
    assert "not bound" in str(refused.value)


@pytest.mark.asyncio
async def test_a_refused_rebind_keeps_the_binding_it_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    _serve_count(monkeypatch, 231)
    state = AgentToolState()
    await bind(state, "GenesByText", _KINASE)
    _refuse_count(monkeypatch, 500)

    with pytest.raises(ModelRetry):
        await bind(state, "GenesByText", {**_KINASE, "text_expression": "protease"})

    [held] = state.operational_spec_draft.criteria
    assert held.param_values["text_expression"].to_wire() == "kinase"
    assert held.result_count == 231


@pytest.mark.asyncio
async def test_a_count_that_did_not_arrive_keeps_the_binding_unmeasured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    _serve_count(monkeypatch, None)
    state = AgentToolState()

    result = await bind(state, "GenesByText", _KINASE)

    assert result.result_count is None
    [held] = state.operational_spec_draft.criteria
    assert held.search_name == "GenesByText"
    assert held.result_count is None
