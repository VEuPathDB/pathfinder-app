"""The mock's parameter edit passes its own why, so the real ``set_criterion``
records the edit over a reason derived from the value it moves."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    StringValue,
    to_wire,
)

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.models.mock.edit_frame import param_edit_call
from pathfinder.ai.models.mock.specs import CriterionReply
from pathfinder.ai.models.mock.strategy_specs import EDITED_MIN_TM, TM_DOMAINS
from pathfinder.ai.tools.standalone._frame_proposals import ParamProposals
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.step_rationale import SearchRationale
from pathfinder.tests._support.recorded_counts import no_measurements
from pathfinder.tests._support.recorded_searches import (
    serve_recorded_plasmodb,
    suite_search,
)
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.models._mock_pins import edit_order
from pathfinder.tests.unit.ai.tools.conftest import serve_no_other_sites
from pathfinder.tests.unit.ai.tools.test_frame_spec import frame_ctx, no_validation

_TM = suite_search("search_genes_by_transmembrane_domains")
_PF = "Plasmodium falciparum 3D7"
_HELD_VALUES: dict[str, ParamValue] = {
    "organism": MultiPickValue(values=[_PF]),
    "min_tm": StringValue(value="2"),
    "max_tm": StringValue(value="99"),
}
_HELD_REASON = SearchRationale(
    search_name=TM_DOMAINS,
    basis="parameter",
    term="Minimum Number of Transmembrane Domains",
    reason="sets min_tm to the value the request states",
    answered=1,
    tool_call_id="call_turn1_read",
    derived_from={name: to_wire(value) for name, value in _HELD_VALUES.items()},
)


def _state() -> AgentToolState:
    held = Criterion(
        id="tm_domains",
        text="GenesByTransmembraneDomains genes",
        search_name=TM_DOMAINS,
        resolved_params={
            name: BoundValue(value=value, source="stated")
            for name, value in _HELD_VALUES.items()
        },
        rationale=_HELD_REASON,
    )
    state = AgentToolState(operational_spec_draft=OperationalSpec(criteria=[held]))
    state.request_messages = ["Change the transmembrane range to 1 to 99."]
    return state


async def test_the_param_edit_is_recorded_with_its_own_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_recorded_plasmodb(monkeypatch, [_TM])
    no_validation(monkeypatch)
    no_measurements(monkeypatch)
    serve_no_other_sites(monkeypatch)
    state = _state()
    sheet = CriterionReply(
        criterion_id="tm_domains",
        search_name=TM_DOMAINS,
        params_template=dict.fromkeys(["organism", "min_tm", "max_tm"]),
    )
    call = param_edit_call(
        edit_order("plasmodb"),
        TM_DOMAINS,
        {"min_tm": EDITED_MIN_TM},
        frozenset({"list_searches"}),
        [sheet],
    )
    args = call.args_as_dict()

    result = returned(
        await set_criterion(
            frame_ctx(state),
            criterion_id=args["criterion_id"],
            text=args["text"],
            search_name=args["search_name"],
            role=args["role"],
            params=TypeAdapter(ParamProposals).validate_python(args["params"]),
            why=SearchChoice.model_validate(args["why"]),
        ),
        SetCriterionResult,
    )

    assert result.resolved_params["min_tm"] == EDITED_MIN_TM
    assert result.rationale is not None
    assert result.rationale.derived_from["min_tm"] == EDITED_MIN_TM


def test_the_why_names_every_moved_parameter() -> None:
    sheet = CriterionReply(
        criterion_id="tm_domains",
        search_name=TM_DOMAINS,
        params_template=dict.fromkeys(["organism", "min_tm", "max_tm"]),
    )

    call = param_edit_call(
        edit_order("plasmodb"),
        TM_DOMAINS,
        {"min_tm": "1", "max_tm": "50"},
        frozenset({"list_searches"}),
        [sheet],
    )

    assert call.args_as_dict()["why"]["reason"] == (
        "sets min_tm, max_tm to the values the request states"
    )
