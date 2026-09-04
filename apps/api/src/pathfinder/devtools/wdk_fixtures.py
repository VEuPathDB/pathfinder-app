"""The pinned WDK responses the hermetic lane reads, and the command that records them.

Every fixture in the store is a response a live site returned. Nothing writes
one by hand: ``record`` refreshes the store, and a confirmed drift is one
command away from the per-PR gate.

Usage::

    python -m pathfinder.devtools.wdk_fixtures list
    python -m pathfinder.devtools.wdk_fixtures record [--only NAME ...]

Recording needs ``VEUPATHDB_AUTH_TOKEN``: VEuPathDB refuses anonymous service
calls. Every request below is user-independent, so no account is addressed.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import sys
from pathlib import Path
from typing import Literal

from assistant_core.platform.types import JSONObject
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from pathfinder.integrations.veupathdb.factory import get_wdk_client

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "wdk"

_TRANSCRIPT = "/record-types/transcript/searches"
_BOOLEAN_TRANSCRIPT = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"


class FixtureRequest(BaseModel):
    """One recorded exchange: what to ask, where, and which rules read it."""

    model_config = ConfigDict(frozen=True)

    name: str
    path: str
    reads: str
    site: str = "plasmodb"
    method: Literal["GET", "POST"] = "GET"
    params: dict[str, str] = Field(default_factory=dict)
    body: JSONObject | None = None

    @property
    def file(self) -> Path:
        return FIXTURE_DIR / f"{self.name}.json"


class FixtureProvenance(BaseModel):
    """Where a recorded response came from, and when."""

    model_config = ConfigDict(frozen=True)

    site: str
    method: str
    url: str
    status: int
    content_type: str
    recorded_at: str
    reads: str


class RecordedWDKResponse(BaseModel):
    """A response as the wire carried it, plus where it came from.

    A body that parses as JSON is stored as JSON; a prose body is stored as
    text. Exactly one of the two is present.
    """

    model_config = ConfigDict(frozen=True)

    provenance: FixtureProvenance
    body: JsonValue = None
    text: str | None = None

    @model_validator(mode="after")
    def _one_body_form(self) -> RecordedWDKResponse:
        if (self.body is None) == (self.text is None):
            msg = (
                f"{self.provenance.url}: a fixture holds a JSON body or prose, not both"
            )
            raise ValueError(msg)
        return self

    def json_body(self) -> JsonValue:
        """The parsed body. A prose fixture raises rather than answer with None."""
        if self.body is None:
            msg = f"{self.provenance.url} recorded prose, not JSON"
            raise TypeError(msg)
        return self.body

    def raw_text(self) -> str:
        """The body as a string, whichever form it was stored in.

        A JSON body is re-serialized, so the characters are the content and
        not the whitespace the server chose.
        """
        return json.dumps(self.body) if self.text is None else self.text


FIXTURES: tuple[FixtureRequest, ...] = (
    FixtureRequest(
        name="search_genes_by_molecular_weight",
        path=f"{_TRANSCRIPT}/GenesByMolecularWeight",
        params={"expandParams": "true"},
        reads="WDK-SEARCH-002, WDK-SEARCH-004, WDK-PARAM-002",
    ),
    FixtureRequest(
        name="search_boolean_transcript",
        path=f"{_TRANSCRIPT}/{_BOOLEAN_TRANSCRIPT}",
        params={"expandParams": "true"},
        reads="WDK-STEP-006, WDK-STEP-008",
    ),
    FixtureRequest(
        name="search_genes_by_orthologs",
        path=f"{_TRANSCRIPT}/GenesByOrthologs",
        params={"expandParams": "true"},
        reads="WDK-STEP-001",
    ),
    FixtureRequest(
        name="search_genes_by_location",
        path=f"{_TRANSCRIPT}/GenesByLocation",
        params={"expandParams": "true"},
        reads="WDK-PARAM-001, WDK-VOCAB-003, WDK-SEARCH-004",
    ),
    FixtureRequest(
        name="search_with_a_hidden_required_parameter",
        path=f"{_TRANSCRIPT}/GenesByPhenotypeEdaSubset_PlasmoDB_Rod_Mal_Phenotype_RSRC",
        params={"expandParams": "true"},
        reads="WDK-PARAM-011",
    ),
    FixtureRequest(
        name="search_genes_by_exon_count",
        path=f"{_TRANSCRIPT}/GenesByExonCount",
        params={"expandParams": "true"},
        reads="WDK-PARAM-003",
    ),
    FixtureRequest(
        name="search_under_the_wrong_record_type",
        path="/record-types/organism/searches/GenesByMolecularWeight",
        reads="WDK-SEARCH-001",
    ),
    FixtureRequest(
        name="search_by_full_name",
        path=f"{_TRANSCRIPT}/GeneQuestions.GenesByMolecularWeight",
        reads="WDK-SEARCH-002",
    ),
    FixtureRequest(
        name="refresh_without_changed_param",
        path=f"{_TRANSCRIPT}/GenesByLocation/refreshed-dependent-params",
        method="POST",
        body={"contextParamValues": {}},
        reads="WDK-VOCAB-006",
    ),
    FixtureRequest(
        name="refresh_with_a_non_string_value",
        path=f"{_TRANSCRIPT}/GenesByLocation/refreshed-dependent-params",
        method="POST",
        body={
            "changedParam": {"name": "organismSinglePick", "value": ["Nope"]},
            "contextParamValues": {"organismSinglePick": "Nope"},
        },
        reads="WDK-PARAM-002, WDK-VOCAB-006",
    ),
    FixtureRequest(
        name="refresh_with_a_value_outside_the_vocabulary",
        path=f"{_TRANSCRIPT}/GenesByLocation/refreshed-dependent-params",
        method="POST",
        body={
            "changedParam": {"name": "organismSinglePick", "value": "Nope"},
            "contextParamValues": {"organismSinglePick": "Nope"},
        },
        reads="WDK-VOCAB-006, WDK-VALID-001, WDK-VALID-006, WDK-HTTP-002",
    ),
    FixtureRequest(
        name="refresh_with_an_unknown_parameter",
        path=f"{_TRANSCRIPT}/GenesByLocation/refreshed-dependent-params",
        method="POST",
        body={
            "changedParam": {"name": "nope", "value": "x"},
            "contextParamValues": {"nope": "x"},
        },
        reads="WDK-VOCAB-006",
    ),
)

_BY_NAME = {fixture.name: fixture for fixture in FIXTURES}


def fixture_request(name: str) -> FixtureRequest:
    """The manifest entry of *name*, or a failure naming the store."""
    if name not in _BY_NAME:
        known = ", ".join(sorted(_BY_NAME))
        msg = f"no WDK fixture named {name!r}; the manifest holds: {known}"
        raise KeyError(msg)
    return _BY_NAME[name]


def load_recorded(name: str) -> RecordedWDKResponse:
    """Read one pinned response, or fail naming the command that records it."""
    path = fixture_request(name).file
    if not path.exists():
        msg = (
            f"{path} is missing; record it with "
            f"`python -m pathfinder.devtools.wdk_fixtures record --only {name}`"
        )
        raise FileNotFoundError(msg)
    return RecordedWDKResponse.model_validate_json(path.read_text())


async def record_one(request: FixtureRequest) -> RecordedWDKResponse:
    """Ask a live site and return the response, without writing it."""
    client = get_wdk_client(request.site)
    probe = await client.probe(
        request.method, request.path, params=dict(request.params), json=request.body
    )
    parsed = probe.json_body()
    recorded = RecordedWDKResponse(
        provenance=FixtureProvenance(
            site=request.site,
            method=probe.method,
            url=probe.url,
            status=probe.status,
            content_type=probe.content_type,
            recorded_at=datetime.datetime.now(tz=datetime.UTC).date().isoformat(),
            reads=request.reads,
        ),
        body=parsed,
        text=None if parsed is not None else probe.text,
    )
    request.file.parent.mkdir(parents=True, exist_ok=True)
    request.file.write_text(
        recorded.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    return recorded


async def record_all(names: list[str]) -> int:
    """Record the named fixtures, or the whole manifest when none are named."""
    wanted = [fixture_request(name) for name in names] if names else list(FIXTURES)
    for request in wanted:
        recorded = await record_one(request)
        size = request.file.stat().st_size
        print(
            f"{request.name}: {recorded.provenance.status} "
            f"{recorded.provenance.content_type} {size}b -> {request.file}"
        )
    return len(wanted)


def _list_fixtures() -> None:
    for request in FIXTURES:
        state = "recorded" if request.file.exists() else "MISSING"
        print(f"{request.name:44} {state:9} {request.reads}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wdk_fixtures", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show the manifest and what is on disk")
    record = sub.add_parser("record", help="refresh the store from live WDK")
    record.add_argument("--only", nargs="*", default=[], metavar="NAME")
    args = parser.parse_args(argv)

    if args.command == "list":
        _list_fixtures()
        return 0
    count = asyncio.run(record_all(args.only))
    print(f"recorded {count} fixture(s) into {FIXTURE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "FIXTURES",
    "FIXTURE_DIR",
    "FixtureProvenance",
    "FixtureRequest",
    "RecordedWDKResponse",
    "fixture_request",
    "load_recorded",
    "record_all",
    "record_one",
]
