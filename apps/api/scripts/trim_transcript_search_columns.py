"""Trim a recorded plasmodb transcript record type into transcript_search_columns.json."""

import argparse
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from veupathdb.model import CamelModel

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "src/pathfinder/tests/fixtures/wdk/transcript_search_columns.json"
)
URL = (
    "https://qa.plasmodb.org/plasmo.qa/service/record-types/transcript?format=expanded"
)
RECORD = (
    "On cedar, with the QA token outside the shell history: "
    f'curl -s -o /tmp/transcript.json -H "Authorization: Bearer $(cat ~/proto/.qa_token)" '
    f'-b "Authorization=$(cat ~/proto/.qa_token)" "{URL}"; then scp '
    "cedar:/tmp/transcript.json here and run this script on it."
)


class _Search(CamelModel):
    model_config = ConfigDict(extra="ignore")

    url_segment: str
    param_names: list[str] = Field(default_factory=list)
    default_attributes: list[str] = Field(default_factory=list)
    dynamic_attributes: list[JsonValue] = Field(default_factory=list)


class _Attribute(CamelModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    display_name: str | None = None
    formats: list[JsonValue] = Field(default_factory=list)
    column_data_type: str
    tools: JsonValue = None


class _RecordType(CamelModel):
    model_config = ConfigDict(extra="ignore")

    url_segment: str
    searches: list[_Search]
    attributes: list[_Attribute]


class _Provenance(BaseModel):
    site: str = "plasmodb"
    method: str = "GET"
    url: str = URL
    status: int = 200
    content_type: str = "application/json"
    recorded_at: str
    reads: str = (
        "step column fit and column counts; searches, defaults, dynamic "
        "attributes, formats, column data types and column tools only"
    )


class _Recording(BaseModel):
    provenance: _Provenance
    body: _RecordType


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, epilog=RECORD)
    parser.add_argument("raw", type=Path, help="the body of the GET, as recorded")
    parser.add_argument("--recorded-at", default=datetime.now(UTC).date().isoformat())
    args = parser.parse_args()
    recording = _Recording(
        provenance=_Provenance(recorded_at=args.recorded_at),
        body=_RecordType.model_validate_json(args.raw.read_text()),
    )
    FIXTURE.write_text(
        recording.model_dump_json(by_alias=True, exclude_none=True, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
