"""The column reports and the catalog of columns plasmodb answered, as recorded."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from pydantic import JsonValue
from veupathdb.testing.wdk_fixtures import RecordedWDKResponse
from veupathdb.wdk import WDKColumnDistribution, WDKRecordType, WDKSearch

from pathfinder.ai.tools.standalone._step_columns import AttributeHistogram
from pathfinder.tests._support.qa_recording import qa_recording

_SUITE = Path(__file__).resolve().parents[1] / "fixtures" / "wdk"
PERCENTILE_SEARCH = (
    "GenesByRNASeqpfal3D7_Gomez-Diaz_asexual_stages_ebi_rnaSeq_RSRCPercentile"
)
# The steps the recorded reports read, as the site numbered them.
TM_STEP = 441031663
PERCENTILE_STEP = 441031673


def recorded_body(fixture: str) -> JsonValue:
    """The body of one recorded response of this suite."""
    recorded = RecordedWDKResponse.model_validate_json(
        qa_recording(_SUITE / f"{fixture}.json").read_text()
    )
    return recorded.json_body()


@cache
def column_catalog() -> WDKRecordType:
    """plasmodb's transcript searches with their columns, and the record columns."""
    return WDKRecordType.model_validate(recorded_body("transcript_search_columns"))


def catalog_search(name: str) -> WDKSearch:
    return next(s for s in column_catalog().searches or [] if s.url_segment == name)


def by_value(fixture: str) -> WDKColumnDistribution:
    return WDKColumnDistribution.model_validate(recorded_body(fixture))


def attribute_histogram(fixture: str) -> AttributeHistogram:
    return AttributeHistogram.model_validate(recorded_body(fixture))
