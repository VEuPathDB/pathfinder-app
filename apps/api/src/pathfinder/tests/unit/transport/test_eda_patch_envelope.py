"""The PATCH envelope both surfaces reduce against."""

from __future__ import annotations

from pathfinder.transport.http.schemas.eda import (
    ConversationEdaResponse,
    EdaAnalysisPatchResponse,
)


def test_the_envelope_always_carries_the_analysis_key() -> None:
    """A missing key and a null analysis are different answers to the tab."""
    schema = EdaAnalysisPatchResponse.model_json_schema()

    assert schema["required"] == ["analysis", "step"]


def test_the_analysis_key_is_nullable() -> None:
    """Unbind answers 200 with analysis null, so the key accepts null."""
    schema = EdaAnalysisPatchResponse.model_json_schema()
    analysis = schema["properties"]["analysis"]

    assert {"type": "null"} in analysis["anyOf"]


def test_an_unbound_answer_serializes_the_analysis_key() -> None:
    dumped = EdaAnalysisPatchResponse(analysis=None, step=None).model_dump(
        by_alias=True
    )

    assert set(dumped) == {"analysis", "step"}
    assert dumped["analysis"] is None


def test_the_conversation_read_always_carries_the_analysis_key() -> None:
    """The tab hydrates from one snapshot, so the key is never absent."""
    schema = ConversationEdaResponse.model_json_schema()

    assert schema["required"] == ["analysis"]
    assert {"type": "null"} in schema["properties"]["analysis"]["anyOf"]


def test_an_unbound_conversation_read_serializes_the_key_as_null() -> None:
    dumped = ConversationEdaResponse(analysis=None).model_dump(by_alias=True)

    assert dumped == {"analysis": None}
