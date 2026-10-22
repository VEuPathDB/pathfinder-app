from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_qualifiers import (
    refuse_a_qualifier_the_search_drops,
)
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.tests._support.orthomcl_site import (
    GROUPS_FROM_SEQUENCES,
    TYPED_GENE_ID,
)
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._orthomcl_site import (
    group_strategy_ctx,
    serve_orthomcl,
)

_TEXT = f"the ortholog group of P. falciparum protein {TYPED_GENE_ID}"


async def test_a_protein_search_is_read_under_sequence_in_a_group_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads = serve_orthomcl(monkeypatch).reads
    state = AgentToolState(request_messages=[_TEXT])

    result = returned(
        await set_criterion(
            group_strategy_ctx(state),
            criterion_id="c_protein",
            text=_TEXT,
            search_name="ByIdList",
            role="seed",
        ),
        SetCriterionResult,
    )

    assert reads == [("sequence", "ByIdList")]
    assert result.sheet_pinned is True
    assert result.params_template == {"source_ids": None}


async def test_a_search_no_record_type_lists_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads = serve_orthomcl(monkeypatch).reads
    state = AgentToolState(request_messages=[_TEXT])

    with pytest.raises(ModelRetry) as refused:
        await set_criterion(
            group_strategy_ctx(state),
            criterion_id="c_protein",
            text=_TEXT,
            search_name="ByProteinId",
            role="seed",
        )

    assert reads == []
    assert refused.value.message == (
        "The search ByProteinId is not served by orthomcl under any record type "
        "(the site's catalog lists it under none). c_protein is not bound. Bind a "
        "search that list_searches or search_for_searches answered with; a "
        "requirement no search on this site answers is site_has_no_search."
    )
    assert state.operational_spec_draft.criteria == []
    assert list(state.unserved_searches) == ["ByProteinId"]
    assert state.refused_searches == {}


async def test_a_transform_reads_the_search_it_maps_under_that_search_s_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads = serve_orthomcl(monkeypatch).reads
    state = AgentToolState(request_messages=[_TEXT])
    state.frame_set_criterion(
        Criterion(id="c_protein", text=_TEXT, search_name="ByIdList", role="seed")
    )

    unread = await refuse_a_qualifier_the_search_drops(
        group_strategy_ctx(state),
        "group",
        GROUPS_FROM_SEQUENCES,
        Criterion(id="c_groups", text=_TEXT, role="transform"),
    )

    assert unread == []
    assert ("sequence", "ByIdList") in reads
    assert ("group", "ByIdList") not in reads
