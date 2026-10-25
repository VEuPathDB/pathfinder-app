from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import httpx
import respx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter
from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    PHYLETIC_EXPRESSION_SEARCH,
    PhyleticExpression,
    PhyleticTree,
)
from veupathdb.wdk import (
    ORTHO_TAXONOMY_RECORD_TYPE,
    ORTHO_TAXONOMY_SEARCH,
    WDKAnswer,
    get_site,
    ortho_taxonomy_of,
)
from veupathdb_mcp.catalog import PhyleticPattern
from veupathdb_mcp.testing import ORTHOMCL_GROUP_CLOUDS

from pathfinder.tests._support.orthomcl_counts import SITE
from pathfinder.tests._support.qa_recording import client_recording, qa_recording

TAXON_PARAM = "taxon_type_ahead"
_UNREAD_SEARCH = "The search details are not part of this recording."

type Codes = frozenset[str]


class SetCodes(BaseModel):
    model_config = ConfigDict(frozen=True)

    tox: tuple[str, ...]
    plas: tuple[str, ...]


class _Tag(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    word: str
    count: int


class _Tags(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    tags: tuple[_Tag, ...]


class _SentConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parameters: dict[str, str]


class _SentReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    search_config: _SentConfig = Field(alias="searchConfig")

    def parameter(self, name: str) -> str:
        return self.search_config.parameters[name]


def _recorded(name: str) -> JsonValue:
    raw: JsonValue = json.loads(
        qa_recording(ORTHOMCL_GROUP_CLOUDS / f"{name}.json").read_text()
    )
    return raw


def set_codes() -> SetCodes:
    return SetCodes.model_validate_json(
        qa_recording(ORTHOMCL_GROUP_CLOUDS / "codes.json").read_text()
    )


def genus_mean() -> PhyleticPattern:
    codes = set_codes()
    return TypeAdapter(PhyleticPattern).validate_python(
        {
            "kind": "compare",
            "left": {"kind": "codes", "codes": sorted(codes.tox)},
            "right": {"kind": "codes", "codes": sorted(codes.plas)},
            "reading": "averages",
            "condition": "more_than",
        }
    )


def cloud_counts(name: str) -> Counter[str]:
    tags = _Tags.model_validate(_recorded(name)).tags
    return Counter({tag.word: tag.count for tag in tags})


def _total(name: str) -> int:
    return WDKAnswer.model_validate(_recorded(name)).meta.records_returned()


def recorded_tree() -> PhyleticTree:
    tree = ortho_taxonomy_of(
        WDKAnswer.model_validate(client_recording("orthomcl_taxonomy").body)
    )
    assert tree is not None
    return tree


def _counted(total: int) -> httpx.Response:
    return httpx.Response(
        200, json={"meta": {"totalCount": total, "responseCount": 0}, "records": []}
    )


@dataclass
class GenusClouds:
    tree: PhyleticTree
    tox: Codes
    plas: Codes
    sent: list[str] = field(default_factory=list)

    def _covered(self, codes: tuple[str, ...]) -> Codes:
        return frozenset(self.tree.genomes_under(list(codes)))

    def groups(self, expression: str) -> int:
        [unit] = PhyleticExpression.parse(expression).units()
        covered = self._covered(unit.codes)
        if unit.taxa:
            assert (unit.op, unit.count) == (">=", 1), expression
            name = {self.tox: "r01a_tox_ge1", self.plas: "r01b_plas_ge1"}[covered]
            return _total(name)
        assert (covered, unit.op) == (self.plas, ">="), expression
        plas = cloud_counts("r04_plas_groupcloud")
        return sum(count >= unit.count for count in plas.values())

    def cloud(self, codes: Codes) -> JsonValue:
        name = {self.tox: "r03_tox_groupcloud", self.plas: "r04_plas_groupcloud"}
        return _recorded(name[codes])

    def records(self, codes: Codes) -> int:
        name = {self.tox: "r03_tox_abbrevcloud", self.plas: "r04_plas_abbrevcloud"}
        return cloud_counts(name[codes]).total()

    async def group_report(self, request: httpx.Request) -> httpx.Response:
        expression = _SentReport.model_validate_json(request.content).parameter(
            PHYLETIC_EXPRESSION_PARAM
        )
        self.sent.append("groups")
        return _counted(self.groups(expression))

    async def record_report(self, request: httpx.Request) -> httpx.Response:
        codes = _SentReport.model_validate_json(request.content).parameter(TAXON_PARAM)
        self.sent.append("records")
        return _counted(self.records(frozenset(json.loads(codes))))

    async def cloud_report(self, request: httpx.Request) -> httpx.Response:
        codes = _SentReport.model_validate_json(request.content).parameter(TAXON_PARAM)
        self.sent.append("cloud")
        return httpx.Response(200, json=self.cloud(frozenset(json.loads(codes))))


@contextmanager
def served_genus_clouds() -> Iterator[GenusClouds]:
    codes = set_codes()
    clouds = GenusClouds(
        tree=recorded_tree(), tox=frozenset(codes.tox), plas=frozenset(codes.plas)
    )
    taxonomy = client_recording("orthomcl_taxonomy")
    site = get_site(SITE)
    service = site.service_url
    sequences = f"{service}/record-types/sequence/searches/ByTaxonomy/reports"
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.get(f"{site.web_base_url}/app").mock(return_value=httpx.Response(200))
        router.post(
            f"{service}/record-types/{ORTHO_TAXONOMY_RECORD_TYPE}/searches/"
            f"{ORTHO_TAXONOMY_SEARCH}/reports/standard"
        ).mock(return_value=httpx.Response(200, json=taxonomy.body))
        router.post(
            f"{service}/record-types/group/searches/"
            f"{PHYLETIC_EXPRESSION_SEARCH}/reports/standard"
        ).mock(side_effect=clouds.group_report)
        router.get(f"{service}/record-types/sequence/searches/ByTaxonomy").mock(
            return_value=httpx.Response(404, text=_UNREAD_SEARCH)
        )
        router.post(f"{sequences}/standard").mock(side_effect=clouds.record_report)
        router.post(f"{sequences}/group_link-wordCloud").mock(
            side_effect=clouds.cloud_report
        )
        yield clouds
