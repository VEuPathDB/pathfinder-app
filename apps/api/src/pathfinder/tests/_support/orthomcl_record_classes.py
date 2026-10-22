from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from veupathdb.testing.wdk_fixtures import RecordedWDKResponse
from veupathdb.wdk import WDKRecordType, WDKSearch

from pathfinder.services.strategies import record_classes
from pathfinder.tests._support.orthomcl_site import BY_ID_LIST, GROUPS_FROM_SEQUENCES
from pathfinder.tests._support.qa_recording import SUITE_WDK_STORE, qa_recording

SEQUENCE = WDKRecordType(
    url_segment="sequence",
    display_name="Protein",
    display_name_plural="Proteins",
    short_display_name="Protein",
)
GROUP = WDKRecordType(
    url_segment="group",
    display_name="Ortholog Group",
    display_name_plural="Ortholog Groups",
    short_display_name="Ortholog Group",
)
PHYLETIC_PATTERN = WDKSearch(
    url_segment="GroupsByPhyleticPattern",
    display_name="Phyletic Pattern",
    output_record_class_name="group",
)
FROM_GROUPS = WDKSearch(
    url_segment="FromGroups",
    display_name="Transform Groups to Proteins",
    output_record_class_name="sequence",
    allowed_primary_input_record_class_names=["group"],
)
SEQUENCE_BOOLEAN = WDKSearch(
    url_segment="boolean_question_SequenceRecordClasses_SequenceRecordClass",
    display_name="Combine Protein results",
    output_record_class_name="sequence",
    allowed_primary_input_record_class_names=["sequence"],
)
SEARCHES = (BY_ID_LIST, GROUPS_FROM_SEQUENCES, PHYLETIC_PATTERN, FROM_GROUPS)


def serve_orthomcl_record_classes(monkeypatch: pytest.MonkeyPatch) -> None:
    listed = (*SEARCHES, SEQUENCE_BOOLEAN)

    async def _searches(_site_id: str, record_type: str) -> list[WDKSearch]:
        return [s for s in listed if s.output_record_class_name == record_type]

    async def _record_types(_site_id: str) -> list[WDKRecordType]:
        return [SEQUENCE, GROUP]

    async def _resolver(_site_id: str) -> Callable[[str], Awaitable[str | None]]:
        async def _listed_under(search_name: str) -> str | None:
            return next(
                (
                    s.output_record_class_name
                    for s in listed
                    if s.url_segment == search_name
                ),
                None,
            )

        return _listed_under

    monkeypatch.setattr(record_classes, "get_raw_searches", _searches)
    monkeypatch.setattr(record_classes, "get_raw_record_types", _record_types)
    monkeypatch.setattr(record_classes, "make_record_type_resolver", _resolver)


def _recorded_record_type(fixture: str) -> WDKRecordType:
    recorded = RecordedWDKResponse.model_validate_json(
        qa_recording(SUITE_WDK_STORE / fixture).read_text()
    )
    return WDKRecordType.model_validate(recorded.json_body())


def recorded_orthomcl_record_types() -> list[WDKRecordType]:
    return [
        _recorded_record_type("orthomcl_group_record_type.json"),
        _recorded_record_type("orthomcl_sequence_record_type.json"),
    ]
