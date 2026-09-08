"""An enrichment exhibit names the call it answers, so its row reads the summary."""

from __future__ import annotations

from uuid import uuid4

from pydantic_ai.ui.vercel_ai.response_types import DataChunk

from pathfinder.ai.tools.standalone import workbench

_RESULT = {
    "geneSetId": "gs-1",
    "geneSetName": "Kinases",
    "geneCount": 42,
    "totalSignificantTerms": 3,
    "analysisTypesRun": ["go_process"],
    "enrichmentResults": [{"analysisType": "go_process", "terms": []}],
}


def test_the_exhibit_carries_the_tool_call_id() -> None:
    chunks = workbench._enrichment_chunks_from_result(
        {"status": "success", "result": _RESULT}, uuid4(), "call_7"
    )

    exhibits = [
        c
        for c in chunks
        if isinstance(c, DataChunk) and c.type == "data-enrichment-results"
    ]
    assert len(exhibits) == 1
    assert exhibits[0].data["toolCallId"] == "call_7"


def test_a_call_with_no_id_leaves_the_field_empty() -> None:
    chunks = workbench._enrichment_chunks_from_result(
        {"status": "success", "result": _RESULT}, uuid4(), None
    )

    exhibits = [
        c
        for c in chunks
        if isinstance(c, DataChunk) and c.type == "data-enrichment-results"
    ]
    assert len(exhibits) == 1
    assert exhibits[0].data["toolCallId"] == ""
