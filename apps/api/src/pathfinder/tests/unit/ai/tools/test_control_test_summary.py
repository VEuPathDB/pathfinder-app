"""What a control test says in one line: the counts, the metrics, the knobs."""

from __future__ import annotations

import pytest
from pydantic_ai import RunContext
from veupathdb_mcp.controls import (
    ControlTestResult,
    IntersectionConfig,
    PositiveControls,
)
from veupathdb_mcp.tool_payloads import ControlOutcome

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone import experiment
from pathfinder.ai.tools.standalone.experiment import _ControlCounts, controls_summary
from pathfinder.services.experiment.published_names import PublishedNames


def test_the_summary_carries_recall_precision_mcc_and_the_knobs() -> None:
    counts = _ControlCounts.model_validate(
        {
            "positiveRecoveredIds": [f"P{index}" for index in range(8)],
            "positiveMissedIds": ["P8", "P9"],
            "negativeAdmittedIds": ["N0", "N1"],
            "negativeExcludedIds": [f"N{index}" for index in range(2, 10)],
            "tunableParameters": ["organism", "scope"],
        }
    )

    assert controls_summary(counts) == (
        "8 of 10 positive controls recovered; "
        "recall 0.80, precision 0.80, MCC 0.60; "
        "tunable parameters: organism, scope"
    )


def test_a_positive_only_test_reports_recall_alone() -> None:
    """No negative ran, so precision 1.00 and MCC 0.00 are not measurements."""
    counts = _ControlCounts.model_validate(
        {
            "positiveRecoveredIds": ["P0", "P1", "P2"],
            "positiveMissedIds": ["P3", "P4"],
            "tunableParameters": [],
        }
    )

    assert controls_summary(counts) == (
        "3 of 5 positive controls recovered; "
        "recall 0.60, no negative controls tested; "
        "no tunable parameters"
    )


def test_a_negatives_only_test_counts_its_negatives() -> None:
    counts = _ControlCounts.model_validate(
        {
            "negativeAdmittedIds": ["PF3D7_0508800", "PF3D7_1215900"],
            "negativeExcludedIds": [f"PF3D7_{n:07d}" for n in range(1, 39)],
            "tunableParameters": [],
        }
    )

    assert controls_summary(counts) == (
        "40 negative controls: 2 returned; no tunable parameters"
    )


def test_a_test_that_ran_no_controls_still_reads() -> None:
    assert controls_summary(_ControlCounts()) == (
        "0 of 0 positive controls recovered; "
        "recall 0.00, no negative controls tested; "
        "no tunable parameters"
    )


async def test_a_standalone_search_test_names_the_searchs_knobs(
    agent_ctx: RunContext[AgentDeps],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def measured(
        config: IntersectionConfig,
        positive_controls: list[str] | None = None,
        negative_controls: list[str] | None = None,
    ) -> ControlTestResult:
        del config, negative_controls
        controls = positive_controls or []
        return ControlTestResult(
            positive=PositiveControls(
                recovered_ids=controls[:1], missed_ids=controls[1:]
            ),
        )

    async def no_export(outcome: ControlOutcome, name: str) -> ControlOutcome:
        del name
        return outcome

    async def published(
        site_id: str, record_type: str, search_name: str
    ) -> PublishedNames:
        del site_id, record_type, search_name
        return PublishedNames()

    async def knobs(site_id: str, record_type: str, search_name: str) -> list[str]:
        del site_id, record_type, search_name
        return ["organism"]

    monkeypatch.setattr(experiment, "run_positive_negative_controls", measured)
    monkeypatch.setattr(experiment, "attach_control_downloads", no_export)
    monkeypatch.setattr(experiment, "published_names", published)
    monkeypatch.setattr(experiment, "tunable_parameters_of_search", knobs)

    answered = await experiment.run_control_tests_on_search(
        agent_ctx,
        target_search_name="GenesByMolecularWeight",
        target_parameters={},
        positive_controls=["PF3D7_1133400", "PF3D7_0102600"],
    )

    assert "tunable parameters: organism" in str(answered.metadata)
