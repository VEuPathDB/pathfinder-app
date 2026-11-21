from __future__ import annotations

import pytest

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone.frame_spec import set_criterion
from strategist.tests._support.catalog_reads import listing
from strategist.tests.unit.ai.tools.test_frame_spec import (
    KINASE_PARAMS,
    default_why,
    frame_ctx,
    genes_by_text,
    serve_search,
)

_SEARCH = "GenesByText"


async def _bind(state: AgentToolState, weight: int | None) -> int | None:
    state.record_catalog_read(listing([_SEARCH]))
    state.request_messages = ["kinases"]
    await set_criterion(
        frame_ctx(state),
        criterion_id="c1",
        text="kinases",
        search_name=_SEARCH,
        params=KINASE_PARAMS,
        why=default_why(_SEARCH, KINASE_PARAMS),
        weight=weight,
    )
    (criterion,) = state.operational_spec_draft.criteria
    return criterion.weight


async def test_a_bound_criterion_holds_its_weight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)

    assert await _bind(AgentToolState(), 2) == 2


async def test_a_bind_without_a_weight_keeps_the_criterions_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    state = AgentToolState()
    await _bind(state, 2)

    assert await _bind(state, None) == 2
