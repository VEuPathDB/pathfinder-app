from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.errors import WDKError

from strategist.ai.tools.standalone import optimization as sweep_tool
from strategist.ai.tools.standalone.control_counts import ControlCounts
from strategist.ai.tools.standalone.experiment import controls_summary
from strategist.ai.tools.standalone.optimization import sweep_can_run
from strategist.domain.evidence import NamedControlSet
from strategist.domain.unread import Unread
from strategist.services.evidence import optimization
from strategist.services.parameter_optimization import tunable
from strategist.tests._support.run_context import lead_run_context
from strategist.tests.unit.ai.tools._strategy_edit_stubs import session_with

_SAVED_SET_ID = "96eaafb0-659c-4041-8bf3-5c66e5a9f95c"
_REFUSED = Unread(reason="HTTP 503: VEuPathDB service error: the site is down")


async def test_a_refused_parameter_read_is_unread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _refuses(*_args: object) -> object:
        msg = "the site is down"
        raise WDKError(msg, status=503)

    monkeypatch.setattr(tunable, "search_parameter_metadata", _refuses)

    read = await optimization.tunable_parameters_of_search(
        "plasmodb", "transcript", "GenesWithSignalPeptide"
    )

    assert read == _REFUSED


def test_a_control_test_says_its_tunable_parameters_were_not_read() -> None:
    counts = ControlCounts(
        positive_recovered_ids=["PF3D7_1133400"],
        positive_missed_ids=[],
        tunable_parameters=_REFUSED,
    )

    assert controls_summary(counts).endswith(
        "tunable parameters not read: HTTP 503: VEuPathDB service error: the site "
        "is down"
    )


async def test_a_sweep_over_an_unread_parameter_list_does_not_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unread(site_id: str, record_type: str, search_name: str) -> Unread:
        del site_id, record_type, search_name
        return _REFUSED

    monkeypatch.setattr(sweep_tool, "tunable_parameters_of_search", _unread)
    session = session_with(
        StrategyStepNode(id="step_sp", search_name="GenesWithSignalPeptide"),
        {"step_sp": 440649693},
    )
    ctx = lead_run_context(strategy_session=session)
    ctx.deps.state.domain.attach_control_set(
        NamedControlSet(id=_SAVED_SET_ID, name="Signal peptide controls")
    )

    with pytest.raises(ModelRetry) as raised:
        await sweep_can_run(
            ctx,
            wdk_step_id=440649693,
            control_set_id=_SAVED_SET_ID,
            parameters=["signalp_version"],
            reply="I will make this change and report what it takes with it.",
        )

    assert str(raised.value) == (
        "The parameters GenesWithSignalPeptide can vary were not read (HTTP 503: "
        "VEuPathDB service error: the site is down). Nothing was started and no "
        "card was shown."
    )
