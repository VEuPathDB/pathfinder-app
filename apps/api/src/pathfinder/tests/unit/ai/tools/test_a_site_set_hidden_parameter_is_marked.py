"""A bound parameter the sheet hides and offers no entries for is the site's
own. The criterion marks it, so no facts row draws it; a hidden parameter with
entries is a choice and stays unmarked."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import VocabOption
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.tests._support.catalog_reads import listing
from pathfinder.tests.unit.ai.tools._rationale_catalog import choice
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    param_info,
    serve_search,
)

_SEARCH = "GenesByOrthologPattern"


def _sheet(context: dict[str, str]) -> list[ParameterInfo]:
    del context
    return [
        param_info(
            "profile_pattern",
            display_name="Profile Pattern",
            is_visible=False,
            default_value="%ecun:N%",
        ),
        param_info(
            "profileset_generic",
            "single-pick-vocabulary",
            display_name="Experiment",
            is_visible=False,
            default_value="a",
            allowed_values=[VocabOption(value=v, display=v) for v in ("a", "b")],
        ),
        param_info("min_count", display_name="Minimum", default_value="1"),
    ]


@pytest.mark.asyncio
async def test_a_hidden_parameter_without_entries_is_marked_as_the_sites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, _sheet, url_segment=_SEARCH, display_name="Profile")
    state = AgentToolState()
    state.record_catalog_read(listing([_SEARCH]))
    state.request_messages = ["genes with at least 1 ortholog"]

    await set_criterion(
        frame_ctx(state),
        criterion_id="c_orth",
        text="genes with at least 1 ortholog",
        search_name=_SEARCH,
        params={"min_count": "1"},
        why=choice("parameter", "Minimum", "the request states at least 1"),
    )

    [criterion] = state.operational_spec_draft.criteria
    assert (
        "profile_pattern" in criterion.resolved_params,
        criterion.hidden_params,
    ) == (True, ["profile_pattern"])
