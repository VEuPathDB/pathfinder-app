"""The check's gaps and caveats are the runtime's: VERIFY's output schema does not
offer them, and the wire the researcher's panel reads carries them."""

from __future__ import annotations

from pydantic import TypeAdapter
from pydantic_ai.tools import GenerateToolJsonSchema

from pathfinder.ai.graph.state import VerificationDigest
from pathfinder.ai.lead.deltas import VerificationDelta


def test_verify_is_not_offered_the_gaps_or_the_caveats() -> None:
    schema = TypeAdapter(VerificationDelta).json_schema(
        schema_generator=GenerateToolJsonSchema
    )
    offered = schema["$defs"]["VerificationDigest"]

    assert {"caveats", "gaps"} & set(offered["properties"]) == set()


def test_the_wire_carries_the_gaps_and_the_caveats() -> None:
    wire = VerificationDigest.model_json_schema(mode="serialization", by_alias=True)

    assert {"caveats", "gaps"} <= set(wire["properties"])
