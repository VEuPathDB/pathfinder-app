"""The pinned EDA responses the hermetic lane reads, and where each came from.

The genomics EDA deployment is one service behind every genomics site host.
A stored body may be trimmed, so ``trim`` says what the copy on disk drops.

Usage::

    python -m pathfinder.tests._support.eda_fixtures list
    python -m pathfinder.tests._support.eda_fixtures record [--only NAME ...]

Recording needs a registered account: ``WDK_TEST_TOKEN``, or
``WDK_TEST_EMAIL``/``WDK_TEST_PASSWORD``. It rewrites the provenance file only;
the bodies are trimmed by hand and are never overwritten.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import sys
from pathlib import Path
from typing import Literal

import structlog
from assistant_core.platform.types import JSONObject
from pydantic import BaseModel, ConfigDict, Field, JsonValue, RootModel
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import get_eda_client
from veupathdb.testing import (
    NO_CREDENTIALS_REASON,
    registered_wdk_token,
)
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

from pathfinder.tests._support.eda_wire import (
    DE_STUDY,
    PHENOTYPE_ENTITY,
    PHENOTYPE_STUDY,
)

logger = structlog.get_logger(__name__)

SITE_ID = "plasmodb"
PROVENANCE_FILE = FIXTURE_DIR / "provenance.json"

_SPECIES = "VAR_035294d0"
_COUNTS_ENTITY = "ENT_fd574cd6"
_SAMPLE_ENTITY = "ENT_8151325d"

_DE_BODY: JSONObject = {
    "studyId": DE_STUDY,
    "filters": [],
    "derivedVariables": [],
    "config": {
        "identifierVariable": {
            "entityId": _COUNTS_ENTITY,
            "variableId": "VEUPATHDB_GENE_ID",
        },
        "valueVariable": {
            "entityId": _COUNTS_ENTITY,
            "variableId": "SEQUENCE_READ_COUNT_SENSE",
        },
        "comparator": {
            "variable": {"entityId": _SAMPLE_ENTITY, "variableId": "VAR_081ab087"},
            "groupA": [{"label": "normal"}],
            "groupB": [{"label": "febrile"}],
        },
        "differentialExpressionMethod": "DESeq",
        "pValueFloor": "1e-200",
    },
}

_SPECIES_FILTER: JSONObject = {
    "entityId": PHENOTYPE_ENTITY,
    "variableId": _SPECIES,
    "type": "stringSet",
    "stringSet": ["P. berghei"],
}


class EdaFixtureRequest(BaseModel):
    """One recorded exchange: what to ask, where, and what the copy drops."""

    model_config = ConfigDict(frozen=True)

    name: str
    path: str
    method: Literal["GET", "POST"] = "GET"
    params: dict[str, str] = Field(default_factory=dict)
    body: JSONObject | None = None
    trim: str = ""

    @property
    def file(self) -> Path:
        return FIXTURE_DIR / f"{self.name}.json"


class EdaFixtureProvenance(BaseModel):
    """Where a recorded response came from, and when."""

    model_config = ConfigDict(frozen=True)

    site: str
    deployment: str
    method: str
    url: str
    status: int
    content_type: str
    body_shape: str
    recorded_at: str
    trim: str = ""


class EdaProvenanceStore(RootModel[dict[str, EdaFixtureProvenance]]):
    """The provenance of every fixture, keyed by name."""


FIXTURES: tuple[EdaFixtureRequest, ...] = (
    EdaFixtureRequest(
        name="studies_list",
        path="/studies",
        trim=(
            "the first 40 studies entries plus every entry whose sha1hash is "
            "the empty string"
        ),
    ),
    EdaFixtureRequest(
        name="permissions",
        path="/permissions",
        trim=(
            "the first 40 perDataset entries, plus every entry that omits "
            "shortDisplayName or description, plus DS_53f554ec6a"
        ),
    ),
    EdaFixtureRequest(name="study_detail_de", path=f"/studies/{DE_STUDY}"),
    EdaFixtureRequest(
        name="study_detail_phenotype", path=f"/studies/{PHENOTYPE_STUDY}"
    ),
    EdaFixtureRequest(
        name="count_unfiltered",
        path=f"/studies/{PHENOTYPE_STUDY}/entities/{PHENOTYPE_ENTITY}/count",
        method="POST",
        body={"filters": []},
    ),
    EdaFixtureRequest(
        name="count_filtered",
        path=f"/studies/{PHENOTYPE_STUDY}/entities/{PHENOTYPE_ENTITY}/count",
        method="POST",
        body={"filters": [_SPECIES_FILTER]},
    ),
    EdaFixtureRequest(
        name="distribution_categorical",
        path=(
            f"/studies/{PHENOTYPE_STUDY}/entities/{PHENOTYPE_ENTITY}"
            f"/variables/{_SPECIES}/distribution"
        ),
        method="POST",
        body={"filters": [], "valueSpec": "count"},
    ),
    EdaFixtureRequest(
        name="compute_job_lookup",
        path="/computes/differentialexpression",
        method="POST",
        params={"autostart": "false"},
        body=_DE_BODY,
    ),
    EdaFixtureRequest(
        name="volcano_statistics",
        path="/computes/differentialexpression/statistics",
        method="POST",
        body=_DE_BODY,
        trim="the first 200 statistics rows plus the one row that omits pValue",
    ),
)

_BY_NAME = {fixture.name: fixture for fixture in FIXTURES}


def fixture_request(name: str) -> EdaFixtureRequest:
    """The manifest entry of *name*, or a failure naming the store."""
    if name not in _BY_NAME:
        known = ", ".join(sorted(_BY_NAME))
        msg = f"no EDA fixture named {name!r}; the manifest holds: {known}"
        raise KeyError(msg)
    return _BY_NAME[name]


def body_shape(body: JsonValue) -> str:
    """The keys a body carries, which is what a hermetic test reads."""
    match body:
        case dict():
            return ",".join(sorted(body))
        case list():
            return f"list[{len(body)}]"
        case _:
            return type(body).__name__


def load_provenance() -> dict[str, EdaFixtureProvenance]:
    """The recorded provenance, or a failure naming the command that writes it."""
    if not PROVENANCE_FILE.exists():
        msg = (
            f"{PROVENANCE_FILE} is missing; record it with "
            "`python -m pathfinder.tests._support.eda_fixtures record`"
        )
        raise FileNotFoundError(msg)
    return EdaProvenanceStore.model_validate_json(PROVENANCE_FILE.read_text()).root


async def _record_one(request: EdaFixtureRequest) -> EdaFixtureProvenance:
    client = get_eda_client(SITE_ID)
    body = await client.request_json(
        request.method, request.path, json=request.body, params=request.params or None
    )
    return EdaFixtureProvenance(
        site=SITE_ID,
        deployment=client.base_url,
        method=request.method,
        url=f"{client.base_url}{request.path}",
        status=200,
        content_type="application/json",
        body_shape=body_shape(body),
        recorded_at=datetime.datetime.now(tz=datetime.UTC).date().isoformat(),
        trim=request.trim,
    )


async def record_all(names: list[str]) -> int:
    """Record the provenance of the named fixtures, or of the whole manifest."""
    token = await registered_wdk_token()
    if token is None:
        raise RuntimeError(NO_CREDENTIALS_REASON)
    wanted = [fixture_request(name) for name in names] if names else list(FIXTURES)
    recorded = dict(load_provenance()) if PROVENANCE_FILE.exists() else {}
    reset = veupathdb_auth_token_ctx.set(token)
    try:
        for request in wanted:
            recorded[request.name] = await _record_one(request)
            logger.info("eda fixture recorded", fixture=request.name)
    finally:
        veupathdb_auth_token_ctx.reset(reset)
    ordered = {name: recorded[name] for name in sorted(recorded)}
    PROVENANCE_FILE.write_text(
        EdaProvenanceStore(ordered).model_dump_json(indent=2) + "\n"
    )
    return len(wanted)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eda_fixtures", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show the manifest and what is on disk")
    record = sub.add_parser("record", help="refresh the provenance from live EDA")
    record.add_argument("--only", nargs="*", default=[], metavar="NAME")
    args = parser.parse_args(argv)

    if args.command == "list":
        for request in FIXTURES:
            logger.info(
                "eda fixture",
                fixture=request.name,
                on_disk=request.file.exists(),
                method=request.method,
                path=request.path,
            )
        return 0
    count = asyncio.run(record_all(args.only))
    logger.info("eda provenance written", count=count, file=str(PROVENANCE_FILE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
