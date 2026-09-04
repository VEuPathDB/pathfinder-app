"""The search-level control test reports the counts the service measured."""

from __future__ import annotations

from typing import Any

import pytest

from pathfinder.ai.tools.standalone import experiment
from pathfinder.domain.parameters.values import StringValue
from pathfinder.services.experiment.types.control_result import (
    ControlSetData,
    ControlTargetData,
    ControlTestResult,
)
from pathfinder.services.tool_payloads import ControlOutcome
from pathfinder.tests.unit.ai.tools.conftest import agent_state_ctx, summary_of


def _measured() -> ControlTestResult:
    return ControlTestResult(
        site_id="plasmodb",
        record_type="transcript",
        target=ControlTargetData(
            search_name="GenesByMolecularWeight",
            parameters={"organism": StringValue(value="Plasmodium falciparum 3D7")},
            step_id=77,
            estimated_size=132,
        ),
        positive=ControlSetData(
            controls_count=3,
            intersection_count=2,
            intersection_ids_sample=["PF3D7_1222600", "PF3D7_1031000"],
            missing_ids_sample=["PF3D7_0000001"],
            target_estimated_size=132,
            recall=2 / 3,
        ),
        negative=ControlSetData(
            controls_count=1,
            intersection_count=0,
            target_estimated_size=132,
            false_positive_rate=0.0,
        ),
    )


@pytest.fixture(autouse=True)
def _measured_service(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run(
        config: Any,
        *,
        positive_controls: list[str] | None = None,
        negative_controls: list[str] | None = None,
    ) -> ControlTestResult:
        del config, positive_controls, negative_controls
        return _measured()

    async def no_export(outcome: ControlOutcome, name: str) -> ControlOutcome:
        del name
        return outcome

    monkeypatch.setattr(experiment, "run_positive_negative_controls", run)
    monkeypatch.setattr(experiment, "attach_control_downloads", no_export)


async def test_the_tool_returns_the_measured_counts_not_empty_defaults() -> None:
    returned = await experiment.run_control_tests_on_search(
        agent_state_ctx(),
        "GenesByMolecularWeight",
        {"organism": StringValue(value="Plasmodium falciparum 3D7")},
        positive_controls=["PF3D7_1222600", "PF3D7_1031000", "PF3D7_0000001"],
        negative_controls=["TGME49_205250"],
    )

    outcome = returned.return_value
    assert isinstance(outcome, ControlOutcome)
    assert outcome.search_name == "GenesByMolecularWeight"
    assert outcome.estimated_size == 132
    assert outcome.positive_intersection == 2
    assert outcome.positive_controls_count == 3
    assert outcome.positive_missing_ids == ["PF3D7_0000001"]
    assert outcome.negative_intersection == 0
    assert outcome.negative_controls_count == 1


async def test_the_summary_names_the_positives_the_search_recovered() -> None:
    returned = await experiment.run_control_tests_on_search(
        agent_state_ctx(),
        "GenesByMolecularWeight",
        {},
        positive_controls=["PF3D7_1222600"],
    )

    assert summary_of(returned).data["summary"] == (
        "2 of 3 positive controls recovered"
    )
