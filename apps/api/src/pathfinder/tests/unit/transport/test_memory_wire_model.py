"""The wire's memory value against the one the runtime stores."""

from __future__ import annotations

from datetime import UTC, datetime

from assistant_core.memory import schemas

from pathfinder.domain.memory import MEMORY_KINDS
from pathfinder.transport.http.schemas.memories import (
    MemoryItem,
    MemoryListResponse,
    MemoryValue,
)


def test_the_wire_carries_every_field_the_runtime_stores() -> None:
    """A field the runtime adds is published here or the release fails."""
    assert set(MemoryValue.model_fields) == set(schemas.MemoryValue.model_fields)


def test_the_wire_publishes_this_products_kinds() -> None:
    """The runtime accepts any name; the wire names the five this product writes."""
    schema = MemoryValue.model_json_schema()

    assert schema["properties"]["kind"]["enum"] == list(MEMORY_KINDS)


def test_the_gene_set_kind_names_a_note_and_not_a_workbench_gene_set() -> None:
    """A kind the model can read as the workbench save is a kind it will misuse."""
    assert "gene_set_note" in MEMORY_KINDS
    assert "gene_set" not in MEMORY_KINDS


def test_the_listing_carries_one_bucket_per_kind() -> None:
    buckets = {
        name
        for name, field in MemoryListResponse.model_fields.items()
        if field.annotation == list[MemoryItem]
    }

    assert buckets == {
        "gene_set_notes",
        "strategies",
        "preferences",
        "knowledge",
        "cases",
    }
    assert len(buckets) == len(MEMORY_KINDS)


def test_a_stored_memory_reads_onto_the_wire_model() -> None:
    stored = schemas.MemoryValue(
        kind="case",
        name="kinome size",
        summary="142 kinases",
        content={"count": 142},
        created_at=datetime(2026, 9, 11, tzinfo=UTC),
    )

    wire = MemoryValue.model_validate(stored, from_attributes=True)

    assert (wire.kind, wire.name, wire.content) == (
        "case",
        "kinome size",
        {"count": 142},
    )
