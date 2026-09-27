"""The value-as-term fault's call is the arc's one binding, and the real
``set_criterion`` accepts it on the recorded signal peptide definition, with the
term corrected to its parameter."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import ParameterInfo, ParamFetcher, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone import frame_spec
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.ai.tools.standalone.catalog import search_for_searches
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.tests._support.recorded_searches import (
    no_count,
    serve_recorded,
    suite_search,
)
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.models._mock_turns import args_of, play
from pathfinder.tests.unit.ai.tools._rationale_catalog import SITE, match
from pathfinder.tests.unit.ai.tools.conftest import (
    agent_run_context,
    serve_no_other_sites,
    summary_of,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    no_validation,
    serve_site_listing,
)

_SIGNAL = suite_search("search_genes_with_signal_peptide")


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded(monkeypatch, [_SIGNAL])

    def _fetch_at(_site: str, _record_type: str, _search: str) -> ParamFetcher:
        async def fetch_at(_context: dict[str, str]) -> list[ParameterInfo]:
            return format_param_info_typed(_SIGNAL.parameters or [])

        return fetch_at

    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)
    no_validation(monkeypatch)
    no_count(monkeypatch)
    serve_site_listing(monkeypatch, SITE)
    serve_no_other_sites(monkeypatch)
    ranked = [
        match(_SIGNAL.url_segment, _SIGNAL.display_name, _SIGNAL.description, 0.52)
    ]
    monkeypatch.setattr(catalog, "search_for_searches", AsyncMock(return_value=ranked))


async def test_the_faulted_term_is_recorded_under_the_parameter_it_is_set_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = play(
        "frame",
        "plasmodb",
        "[[arc:single]][[fault:value-as-term]]",
        work_order="Frame work order: mock frame",
    )
    (args,) = [a for a in args_of(calls, "set_criterion") if "params" in a]
    _serve(monkeypatch)
    state = AgentToolState()
    await search_for_searches(
        agent_run_context(agent_state=state, tool_call_id="call_read"),
        query="predicted signal peptide",
    )

    answer = await set_criterion(
        frame_ctx(state),
        criterion_id=args["criterion_id"],
        text=args["text"],
        search_name=args["search_name"],
        role=args["role"],
        params=args["params"],
        why=SearchChoice.model_validate(args["why"]),
    )
    result = returned(answer, SetCriterionResult)

    assert args["why"]["term"] == "SignalP-6.0"
    assert result.rationale is not None
    assert (result.rationale.basis, result.rationale.term, result.corrections) == (
        "parameter",
        "Version",
        ["why.term corrected to Version: SignalP-6.0 is its value"],
    )
    assert str(summary_of(answer).data["summary"]).endswith(
        "sets Version; why.term corrected to Version: SignalP-6.0 is its value"
    )
