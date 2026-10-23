from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import httpx
import respx
from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    PHYLETIC_EXPRESSION_SEARCH,
    PhyleticExpression,
)
from veupathdb.wdk import (
    ORTHO_TAXONOMY_RECORD_TYPE,
    ORTHO_TAXONOMY_SEARCH,
    get_site,
)
from veupathdb_mcp.testing import ORTHOMCL_COUNTS

from pathfinder.tests._support.qa_recording import client_recording, qa_recording

SITE = "orthomcl"
LADDER = "orthomcl_protein_count_ladder.json"
CLADE_ONLY = "orthomcl_clade_only_counts.json"
EVERY_SPECIES = "orthomcl_every_species_counts.json"
CRYPTOSPORIDIUM = [
    "cand",
    "cbov",
    "choi",
    "chot",
    "chom",
    "chod",
    "cmel",
    "cmtu",
    "cmur",
    "cpia",
    "cpib",
    "cpar",
    "crya",
    "cser",
    "cspi",
    "cscp",
    "ctyz",
    "cubi",
]
_UNAVAILABLE = "Service Unavailable"


class RecordedReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    expression: str
    total: int


class _SentConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parameters: dict[str, str]


class _SentReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    search_config: _SentConfig = Field(alias="searchConfig")


class CountRecording(BaseModel):
    model_config = ConfigDict(frozen=True)

    site: str
    build: str
    search: str
    reports: tuple[RecordedReport, ...]


def count_recording(name: str) -> CountRecording:
    return CountRecording.model_validate_json(
        qa_recording(ORTHOMCL_COUNTS / name).read_text()
    )


type Reading = frozenset[frozenset[tuple[frozenset[str], str, int, bool]]]


def _reading(expression: str) -> Reading:
    root = PhyleticExpression.parse(expression).site_reading().root
    return frozenset(
        frozenset(
            (frozenset(unit.codes), unit.op, unit.count, unit.taxa)
            for unit in PhyleticExpression(root=term).units()
        )
        for term in root.operands("OR")
    )


def same_reading(first: str, second: str) -> bool:
    return _reading(first) == _reading(second)


@dataclass
class ReplayedCounts:
    pending: list[RecordedReport]
    delay: float = 0.0
    status: int = 200
    sent: list[str] = field(default_factory=list)

    async def answer(self, request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(self.delay)
        sent = _SentReport.model_validate_json(request.content)
        expression = sent.search_config.parameters[PHYLETIC_EXPRESSION_PARAM]
        self.sent.append(expression)
        if self.status != httpx.codes.OK:
            return httpx.Response(self.status, text=_UNAVAILABLE)
        recorded = self.pending.pop(0)
        assert same_reading(expression, recorded.expression), expression
        return httpx.Response(
            200,
            json={
                "meta": {"totalCount": recorded.total, "responseCount": 0},
                "records": [],
            },
        )


@contextmanager
def replayed_counts(
    name: str, *, start: int = 0, delay: float = 0.0, status: int = 200
) -> Iterator[ReplayedCounts]:
    recording = count_recording(name)
    taxonomy = client_recording("orthomcl_taxonomy")
    replay = ReplayedCounts(
        pending=list(recording.reports[start:]), delay=delay, status=status
    )
    site = get_site(SITE)
    service = site.service_url
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.get(f"{site.web_base_url}/app").mock(return_value=httpx.Response(200))
        router.post(
            f"{service}/record-types/{ORTHO_TAXONOMY_RECORD_TYPE}/searches/"
            f"{ORTHO_TAXONOMY_SEARCH}/reports/standard"
        ).mock(return_value=httpx.Response(200, json=taxonomy.body))
        router.post(
            f"{service}/record-types/group/searches/"
            f"{PHYLETIC_EXPRESSION_SEARCH}/reports/standard"
        ).mock(side_effect=replay.answer)
        yield replay
