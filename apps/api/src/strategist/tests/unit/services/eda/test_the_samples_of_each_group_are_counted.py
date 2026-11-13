from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from structlog.testing import capture_logs
from veupathdb.domain import validate_compute_config
from veupathdb.eda import (
    EdaClient,
    EdaDifferentialExpressionConfig,
    EdaStudyDetail,
    EdaSubsetDescriptor,
)

from strategist.services.eda.compute import comparison_of
from strategist.services.eda.group_samples import (
    GroupSamples,
    group_samples,
    too_few_samples,
)
from strategist.tests._support.eda_wire import wire_eda_client

RECORDED = json.loads(
    (
        Path(__file__).parents[3] / "fixtures" / "eda" / "group_sample_counts.json"
    ).read_text()
)
CASES = {case["name"]: case for case in RECORDED["cases"]}
HOST = "hostdb_sporozoite_timepoints"
UPSTREAM_TEXT = "upstream secret text"
COUNT_PAIRS = [
    (0, 0),
    (0, 1),
    (0, 2),
    (3, 0),
    (1, 1),
    (1, 3),
    (31, 1),
    (2, 1),
    (2, 2),
    (4, 31),
]


def _config(case: dict[str, Any]) -> EdaDifferentialExpressionConfig:
    entity = case["valueEntity"]
    return EdaDifferentialExpressionConfig.model_validate(
        {
            "identifier_variable": {
                "entity_id": entity,
                "variable_id": "VEUPATHDB_GENE_ID",
            },
            "value_variable": {
                "entity_id": entity,
                "variable_id": case["valueVariable"],
            },
            "comparator": {
                "variable": {
                    "entity_id": case["sampleEntity"],
                    "variable_id": case["comparatorVariable"],
                },
                "group_a": [{"label": label} for label in case["groupA"]],
                "group_b": [{"label": label} for label in case["groupB"]],
            },
            "differential_expression_method": "DESeq",
        }
    )


def _samples(group_a: int, group_b: int) -> GroupSamples:
    config = _config(CASES["tritrypdb_procyclic_bloodstream"])
    return GroupSamples(
        group_a=group_a, group_b=group_b, comparison=comparison_of(config)
    )


def _recorded_site(
    case: dict[str, Any], requests: list[httpx.Request]
) -> httpx.MockTransport:
    def group_filter(labels: list[str]) -> dict[str, Any]:
        return {
            "entityId": case["sampleEntity"],
            "variableId": case["comparatorVariable"],
            "type": "stringSet",
            "stringSet": labels,
        }

    answers = [
        ([*case["subset"], group_filter(case["groupA"])], case["counts"]["groupA"]),
        ([*case["subset"], group_filter(case["groupB"])], case["counts"]["groupB"]),
    ]

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        filters = json.loads(request.content)["filters"]
        count = next(count for sent, count in answers if sent == filters)
        return httpx.Response(200, json={"count": count})

    return httpx.MockTransport(respond)


async def _read(
    monkeypatch: pytest.MonkeyPatch,
    transport: httpx.MockTransport,
    case: dict[str, Any],
) -> GroupSamples | None:
    client = EdaClient(base_url="https://qa.plasmodb.org/eda", transport=transport)
    wire_eda_client(monkeypatch, client)
    samples = await group_samples(
        case["site"],
        study=EdaStudyDetail.model_validate(case["study"]),
        config=_config(case),
        filters=EdaSubsetDescriptor.model_validate(
            {"descriptor": case["subset"]}
        ).descriptor,
    )
    await client.close()
    return samples


@pytest.mark.parametrize(
    ("name", "group_a", "group_b", "refused"),
    [
        ("tritrypdb_procyclic_bloodstream", 1, 1, True),
        ("microsporidiadb_8_64_hour", 1, 1, True),
        ("fungidb_normoxia_hypoxia_t12", 0, 1, True),
        (HOST, 4, 31, False),
    ],
)
async def test_a_recorded_study_counts_the_samples_of_each_group(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    group_a: int,
    group_b: int,
    refused: bool,
) -> None:
    case = CASES[name]
    study = EdaStudyDetail.model_validate(case["study"])
    assert validate_compute_config(study, _config(case)) == []
    requests: list[httpx.Request] = []

    samples = await _read(monkeypatch, _recorded_site(case, requests), case)

    assert samples is not None
    assert (samples.group_a, samples.group_b) == (group_a, group_b)
    assert [request.url.path for request in requests] == [
        f"/eda/studies/{case['studyId']}/entities/{case['sampleEntity']}/count"
    ] * 2
    assert (too_few_samples(samples, method="DESeq") is not None) is refused


def test_no_replicate_in_either_group_is_refused_with_both_counts() -> None:
    refusal = too_few_samples(_samples(1, 1), method="DESeq")

    assert str(refusal) == (
        "No DESeq job started. In this analysis, group A (procyclic form) holds "
        "1 sample and group B (bloodstream form) holds 1 sample. A group with no "
        "sample, or two groups with no replicate in either, is not sent to DESeq. "
        "A repeat of this call gets the same answer. Tell the researcher these "
        "counts, or widen the subset or choose groups that hold more samples."
    )


def test_deseq_refuses_an_empty_group_or_no_replicate_and_runs_the_rest() -> None:
    assert [
        pair
        for pair in COUNT_PAIRS
        if too_few_samples(_samples(*pair), method="DESeq") is not None
    ] == [(0, 0), (0, 1), (0, 2), (3, 0), (1, 1)]


def test_limma_is_not_refused() -> None:
    assert [
        pair
        for pair in COUNT_PAIRS
        if too_few_samples(_samples(*pair), method="limma") is not None
    ] == []


def test_no_count_refuses_nothing() -> None:
    assert [
        too_few_samples(None, method="DESeq"),
        too_few_samples(None, method="limma"),
    ] == [None, None]


def test_the_counts_are_stated_with_the_labels_of_each_group() -> None:
    assert _samples(4, 0).stated == (
        "In this analysis, group A (procyclic form) holds 4 samples and group B "
        "(bloodstream form) holds 0 samples."
    )


@pytest.mark.parametrize(
    "respond",
    [
        lambda _request: httpx.Response(500, text=UPSTREAM_TEXT),
        lambda _request: httpx.Response(404, text=UPSTREAM_TEXT),
        lambda _request: httpx.Response(200, json={"rows": UPSTREAM_TEXT}),
    ],
)
async def test_a_count_read_that_fails_counts_nothing_and_logs_no_upstream_text(
    monkeypatch: pytest.MonkeyPatch,
    respond: Callable[[httpx.Request], httpx.Response],
) -> None:
    with capture_logs() as logs:
        samples = await _read(monkeypatch, httpx.MockTransport(respond), CASES[HOST])

    assert [samples] == [None]
    assert [log["event"] for log in logs if log["log_level"] == "warning"] == [
        "Group samples were not read"
    ]
    assert UPSTREAM_TEXT not in repr(logs)


async def test_a_count_read_that_times_out_counts_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(UPSTREAM_TEXT, request=request)

    samples = await _read(monkeypatch, httpx.MockTransport(respond), CASES[HOST])

    assert [samples] == [None]


def _unreachable(request: httpx.Request) -> httpx.Response:
    raise AssertionError(request.url.path)


async def test_a_value_entity_with_no_parent_has_no_samples_to_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = json.loads(json.dumps(CASES[HOST]))
    case["valueEntity"] = case["sampleEntity"]

    samples = await _read(monkeypatch, httpx.MockTransport(_unreachable), case)

    assert [samples] == [None]


@pytest.mark.parametrize(
    ("key", "unknown"),
    [("sampleEntity", "ENT_not_in_the_study"), ("comparatorVariable", "VAR_unknown")],
)
async def test_a_comparator_the_study_does_not_hold_is_not_counted(
    monkeypatch: pytest.MonkeyPatch, key: str, unknown: str
) -> None:
    case = json.loads(json.dumps(CASES[HOST]))
    case[key] = unknown

    samples = await _read(monkeypatch, httpx.MockTransport(_unreachable), case)

    assert [samples] == [None]


async def test_a_comparator_that_is_not_a_string_is_not_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = json.loads(json.dumps(CASES[HOST]))
    comparator = next(
        variable
        for variable in case["study"]["rootEntity"]["variables"]
        if variable["id"] == case["comparatorVariable"]
    )
    comparator["type"] = "integer"

    samples = await _read(monkeypatch, httpx.MockTransport(_unreachable), case)

    assert [samples] == [None]
