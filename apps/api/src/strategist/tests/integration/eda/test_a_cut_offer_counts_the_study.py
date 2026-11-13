from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import EdaClient, EdaStudyDetailResponse
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

from strategist.domain.strategy.question_options import TailRule
from strategist.services.eda import authoring, catalog
from strategist.services.eda.cut_offer import (
    OfferedCut,
    study_cut_question,
    study_tail_edges,
)
from strategist.tests._support.qa_recording import qa_recording

pytestmark = pytest.mark.asyncio

_DATASET = "DS_53f554ec6a"
_STUDY = "STUDY_53f554ec6a"
_ENTITY = "GENE_PHENOTYPE_DATA_ENTITY"
_SPECIES = "VAR_035294d0"
_SCORE = "VAR_score"

# The continuous body the client's knowledge bundle records for a five-unit
# binSpec, served for a score variable added to the recorded phenotype study.
_CONTINUOUS = {
    "histogram": [
        {"value": 13, "binStart": "0.0", "binEnd": "5.0", "binLabel": "[0.0,5.0)"},
        {"value": 3254, "binStart": "5.0", "binEnd": "10.0", "binLabel": "[5.0,10.0)"},
        {
            "value": 31990,
            "binStart": "10.0",
            "binEnd": "15.0",
            "binLabel": "[10.0,15.0)",
        },
        {
            "value": 1313,
            "binStart": "15.0",
            "binEnd": "20.0",
            "binLabel": "[15.0,20.0)",
        },
        {"value": 0, "binStart": "20.0", "binEnd": "25.0", "binLabel": "[20.0,25.0)"},
    ],
    "statistics": {
        "subsetSize": 48721,
        "numVarValues": 36570,
        "numDistinctValues": 174,
        "numDistinctEntityRecords": 36570,
        "numMissingCases": 12151,
    },
}


# What the service counts for each range filter on the score, ends included.
_SELECTED = {(0.0, 10.0): 3301, (0.0, 15.0): 35290, (10.0, 25.0): 33344}


def _fixture(name: str) -> Any:
    return json.loads(qa_recording(FIXTURE_DIR / name).read_text())


def _study_with_a_score() -> dict[str, Any]:
    detail: dict[str, Any] = _fixture("study_detail_phenotype.json")
    detail["study"]["rootEntity"]["variables"].append(
        {
            "id": _SCORE,
            "providerLabel": '["score"]',
            "displayName": "Phenotype Score",
            "type": "number",
            "dataShape": "continuous",
            "distributionDefaults": {"rangeMin": 0, "rangeMax": 25, "binWidth": 5},
        }
    )
    return detail


def _distributions() -> dict[str, Any]:
    return {
        _SPECIES: _fixture("distribution_categorical.json"),
        _SCORE: _CONTINUOUS,
    }


def _reads() -> dict[str, Any]:
    return {
        "/eda/studies": _fixture("studies_list.json"),
        f"/eda/studies/{_STUDY}": _study_with_a_score(),
    }


def _counted(body: dict[str, Any], counts: list[tuple[float, float]]) -> int:
    ranges = [
        (f["min"], f["max"]) for f in body["filters"] if f["type"] == "numberRange"
    ]
    counts.extend(ranges)
    return sum(_SELECTED[r] for r in ranges)


def _route(
    asked: list[dict[str, Any]], counts: list[tuple[float, float]]
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        variable = path.removesuffix("/distribution").rsplit("/", 1)[-1]
        if path.endswith("/distribution") and variable in _distributions():
            asked.append(json.loads(request.content))
            return httpx.Response(200, json=_distributions()[variable])
        if path.endswith("/permissions"):
            return httpx.Response(200, json=_fixture("permissions.json"))
        if path.endswith("/count"):
            body = json.loads(request.content)
            return httpx.Response(200, json={"count": _counted(body, counts)})
        if path in _reads():
            return httpx.Response(200, json=_reads()[path])
        return httpx.Response(404, json={"status": "not-found"})

    return httpx.MockTransport(handler)


@pytest.fixture
def counts() -> list[tuple[float, float]]:
    return []


@pytest.fixture
def asked(
    monkeypatch: pytest.MonkeyPatch, counts: list[tuple[float, float]]
) -> Iterator[list[dict[str, Any]]]:
    seen: list[dict[str, Any]] = []
    client = EdaClient(
        base_url="https://qa.plasmodb.org/eda", transport=_route(seen, counts)
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _s: client)
    monkeypatch.setattr(authoring, "get_eda_client", lambda _s: client)
    token = veupathdb_auth_token_ctx.set("t")
    yield seen
    veupathdb_auth_token_ctx.reset(token)


async def test_the_offer_counts_the_tails_and_the_classes_of_the_whole_study(
    asked: list[dict[str, Any]], counts: list[tuple[float, float]]
) -> None:
    study = EdaStudyDetailResponse.model_validate(_study_with_a_score()).study
    question = await study_cut_question(
        "plasmodb",
        dataset_id=_DATASET,
        study=study,
        cut=OfferedCut(
            entity_id=_ENTITY,
            variable_id=_SCORE,
            variable_name="Phenotype Score",
            numeric=True,
            classes=[(_SPECIES, "Species")],
        ),
    )

    assert [o.label for o in question.options] == [
        "Lowest 9.0% of Phenotype Score: at most 10 (3301 genes)",
        "Lowest 96.5% of Phenotype Score: at most 15 (35290 genes)",
        "Highest 91.2% of Phenotype Score: at least 10 (33344 genes)",
        "Species: P. berghei (4011 genes)",
        "Species: P. falciparum (4130 genes)",
        "Species: P. yoelii (268 genes)",
    ]
    assert [(body["filters"], "binSpec" in body) for body in asked] == [
        ([], True),
        ([], False),
    ]
    assert counts == [(0.0, 10.0), (0.0, 15.0), (10.0, 25.0)]


async def test_a_held_rule_reads_the_studys_own_edge(
    asked: list[dict[str, Any]], counts: list[tuple[float, float]]
) -> None:
    edges = await study_tail_edges(
        "plasmodb",
        dataset_id=_DATASET,
        study=EdaStudyDetailResponse.model_validate(_study_with_a_score()).study,
        entity_id=_ENTITY,
        variable_id=_SCORE,
        rules={
            "low": TailRule(end="low", percent=5),
            "high": TailRule(end="high", percent=10),
        },
    )

    assert {label: (e.bound, e.count, e.total) for label, e in edges.items()} == {
        "low": (10.0, 3301, 36570),
        "high": (10.0, 33344, 36570),
    }
    assert [body["filters"] for body in asked] == [[]]
    assert counts == [(0.0, 10.0), (10.0, 25.0)]
