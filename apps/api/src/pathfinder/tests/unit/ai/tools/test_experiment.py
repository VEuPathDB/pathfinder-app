"""The control tests report the counts the service measured, and the
durable answer carries them as an exhibit."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

import pytest
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk, DataChunk
from veupathdb.domain.parameters import StringValue
from veupathdb_mcp.controls import ControlSetData, ControlTargetData, ControlTestResult
from veupathdb_mcp.tool_payloads import ControlOutcome

from pathfinder.ai.tools.standalone import experiment
from pathfinder.services.experiment.published_names import PublishedNames
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context, summary_of


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

    async def published(
        site_id: str, record_type: str, search_name: str
    ) -> PublishedNames:
        del site_id, record_type, search_name
        return PublishedNames(
            label="Genes by Molecular Weight",
            parameter_labels={"organism": "Organism"},
        )

    async def knobs(site_id: str, record_type: str, search_name: str) -> list[str]:
        del site_id, record_type, search_name
        return ["organism"]

    monkeypatch.setattr(experiment, "tunable_parameters_of_search", knobs)
    monkeypatch.setattr(experiment, "run_positive_negative_controls", run)
    monkeypatch.setattr(experiment, "attach_control_downloads", no_export)
    monkeypatch.setattr(experiment, "published_names", published)


async def test_the_tool_returns_the_measured_counts_not_empty_defaults() -> None:
    returned = await experiment.run_control_tests_on_search(
        agent_run_context(),
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
        agent_run_context(),
        "GenesByMolecularWeight",
        {},
        positive_controls=["PF3D7_1222600"],
    )

    assert summary_of(returned).data["summary"] == (
        "2 of 3 positive controls recovered; "
        "recall 0.67, precision 1.00, MCC 0.58; "
        "tunable parameters: organism"
    )


def _durable_result(**overrides: Any) -> dict[str, Any]:
    """The dict shape the worker answers ``run_control_tests_on_step`` with."""
    outcome = ControlOutcome(
        step_id=440299573,
        search_name="GenesByMolecularWeight",
        parameters={"organism": StringValue(value="Plasmodium falciparum 3D7")},
        estimated_size=132,
        positive_intersection=2,
        positive_controls_count=3,
        positive_recall=2 / 3,
        positive_intersection_ids=["PF3D7_1222600", "PF3D7_1031000"],
        positive_missing_ids=["PF3D7_0000001"],
        negative_intersection=0,
        negative_controls_count=1,
        negative_false_positive_rate=0.0,
    )
    dumped = outcome.model_dump(by_alias=True, exclude_none=True, mode="json")
    dumped["targetLabel"] = "Genes by Molecular Weight"
    dumped["parameterLabels"] = {"organism": "Organism"}
    dumped.update(overrides)
    return {"status": "success", "result": dumped}


def _data_chunks(chunks: Sequence[BaseChunk]) -> list[DataChunk]:
    """Every chunk the tool emitted, read as the data chunk it is."""
    return [DataChunk.model_validate(chunk) for chunk in chunks]


def _exhibits(chunks: Sequence[BaseChunk]) -> list[DataChunk]:
    return [
        chunk
        for chunk in _data_chunks(chunks)
        if chunk.type == "data-control-test-results"
    ]


def test_the_durable_answer_emits_the_exhibit_beside_the_summary() -> None:
    chunks = experiment._control_test_chunks_from_result(
        _durable_result(),
        UUID("3d221443-0074-47d8-8300-addadd147989"),
        "call_sLwqd6ToSyX9TDfOm62FTIT6",
    )

    kinds = [chunk.type for chunk in _data_chunks(chunks)]
    assert kinds == ["data-control-test-results", "data-tool-summary"]
    exhibit = _exhibits(chunks)[0].data
    assert exhibit["taskId"] == "3d221443-0074-47d8-8300-addadd147989"
    assert exhibit["toolCallId"] == "call_sLwqd6ToSyX9TDfOm62FTIT6"
    assert exhibit["targetStepId"] == 440299573
    assert exhibit["targetLabel"] == "Genes by Molecular Weight"
    assert exhibit["targetEstimatedSize"] == 132
    assert exhibit["targetParameters"] == [
        {"label": "Organism", "value": "Plasmodium falciparum 3D7"}
    ]
    assert exhibit["positive"] == {
        "controlsCount": 3,
        "intersectionCount": 2,
        "recall": 2 / 3,
        "falsePositiveRate": None,
        "hitIds": ["PF3D7_1222600", "PF3D7_1031000"],
        "missedIds": ["PF3D7_0000001"],
    }
    assert exhibit["negative"] == {
        "controlsCount": 1,
        "intersectionCount": 0,
        "recall": None,
        "falsePositiveRate": 0.0,
        "hitIds": [],
        "missedIds": [],
    }


def test_the_exhibit_omits_a_control_set_the_test_did_not_run() -> None:
    answer = _durable_result()
    for key in (
        "negativeIntersection",
        "negativeControlsCount",
        "negativeFalsePositiveRate",
    ):
        answer["result"].pop(key, None)

    chunks = experiment._control_test_chunks_from_result(answer, UUID(int=1), "call_1")

    exhibit = _exhibits(chunks)[0].data
    assert exhibit["negative"] is None
    assert exhibit["positive"]["controlsCount"] == 3


def test_a_failed_durable_answer_emits_nothing() -> None:
    chunks = experiment._control_test_chunks_from_result(
        {"status": "failed", "result": {}}, UUID(int=1), "call_1"
    )

    assert chunks == []


def test_the_exhibit_is_dropped_when_no_call_can_carry_it() -> None:
    chunks = experiment._control_test_chunks_from_result(
        _durable_result(), UUID(int=1), None
    )

    assert chunks == []


def test_the_exhibit_never_shows_a_search_url_segment() -> None:
    answer = _durable_result()
    answer["result"]["targetLabel"] = ""

    chunks = experiment._control_test_chunks_from_result(answer, UUID(int=2), "call_2")

    exhibit = _exhibits(chunks)[0].data
    assert exhibit["targetLabel"] == "step 440299573"


def test_a_parameter_keeps_its_wdk_name_when_the_run_resolved_none() -> None:
    answer = _durable_result()
    answer["result"]["parameterLabels"] = {}

    chunks = experiment._control_test_chunks_from_result(answer, UUID(int=3), "call_3")

    exhibit = _exhibits(chunks)[0].data
    assert exhibit["targetParameters"] == [
        {"label": "organism", "value": "Plasmodium falciparum 3D7"}
    ]


def test_a_long_parameter_value_is_cut_to_a_readable_length() -> None:
    ids = ",".join(f"PF3D7_{index:07d}" for index in range(40))
    answer = _durable_result()
    answer["result"]["parameters"] = {"dsGeneIds": {"type": "string", "value": ids}}

    chunks = experiment._control_test_chunks_from_result(answer, UUID(int=4), "call_4")

    shown = _exhibits(chunks)[0].data["targetParameters"][0]["value"]
    assert shown.endswith(" ...")
    assert len(shown) <= experiment.VALUE_CHARS + len(" ...")


async def test_a_search_level_test_leaves_the_same_exhibit() -> None:
    returned = await experiment.run_control_tests_on_search(
        agent_run_context(),
        "GenesByMolecularWeight",
        {"organism": StringValue(value="Plasmodium falciparum 3D7")},
        positive_controls=["PF3D7_1222600"],
    )

    exhibits = [
        chunk
        for chunk in returned.metadata or []
        if chunk.type == "data-control-test-results"
    ]
    assert len(exhibits) == 1
    exhibit = exhibits[0].data
    assert exhibit["taskId"] == ""
    assert exhibit["targetLabel"] == "Genes by Molecular Weight"
    assert exhibit["targetParameters"] == [
        {"label": "Organism", "value": "Plasmodium falciparum 3D7"}
    ]
    assert exhibit["positive"]["hitIds"] == ["PF3D7_1222600", "PF3D7_1031000"]
