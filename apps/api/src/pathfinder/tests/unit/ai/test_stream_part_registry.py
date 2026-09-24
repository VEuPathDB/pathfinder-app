"""Tests for the stream-part registry behind the generated schema index."""

import pytest
from assistant_core.conversation.stream_parts.core_parts import (
    register_core_stream_parts,
)
from assistant_core.conversation.stream_parts.registry import (
    DuplicateStreamPartError,
    InvalidStreamPartNameError,
    StreamPartRegistry,
)
from pydantic import BaseModel
from pydantic.alias_generators import to_camel

from pathfinder.ai.strategy_stream_parts import register_strategy_stream_parts
from pathfinder.main import create_app

# The set the schema index carried before the registry existed. A registration
# that disappears must fail here, not silently shrink the generated types.
PINNED_SCHEMA_NAMES = frozenset(
    {
        "graph_snapshot",
        "graph_cleared",
        "strategy_meta",
        "strategy_link",
        "consult_question",
        "user_question_answer",
        "variant_comparison",
        "scored_comparison",
        "gene_set",
        "turn_usage",
        "background_task_started",
        "task_progress",
        "task_completed",
        "control_test_results",
        "evidence_card",
        "sub_agent_call",
        "sub_agent_step",
        "turn_stopped",
        "turn_failed",
        "turn_status",
        "conversation_title",
        "lead_usage",
        "strategy_revision",
        "tool_summary",
        "ledger_update",
        "memory_retrieved",
        "scratchpad_updated",
        "proposal",
    }
)

PINNED_CORE_KINDS = frozenset(
    {
        "data-background-task-started",
        "data-task-progress",
        "data-task-completed",
        "data-turn-usage",
        "data-turn-status",
        "data-turn-stopped",
        "data-turn-failed",
        "data-conversation-title",
        "data-tool-summary",
        "data-scratchpad-updated",
    }
)

PINNED_STRATEGY_KINDS = frozenset(
    {
        "data-graph-snapshot",
        "data-graph-cleared",
        "data-strategy-meta",
        "data-strategy-link",
        "data-strategy-revision",
        "data-gene-set",
        "data-control-test-results",
        "data-evidence-card",
        "data-variant-comparison",
        "data-scored-comparison",
        "data-ledger-update",
        "data-memory-retrieved",
        "data-lead-usage",
        "data-sub-agent-call",
        "data-sub-agent-step",
    }
)


class _Payload(BaseModel):
    value: str = ""


def _full_registry() -> StreamPartRegistry:
    registry = StreamPartRegistry()
    register_core_stream_parts(registry)
    register_strategy_stream_parts(registry)
    return registry


def test_register_rejects_a_duplicate_kind() -> None:
    registry = StreamPartRegistry()
    registry.register("data-thing", _Payload)
    with pytest.raises(DuplicateStreamPartError):
        registry.register("data-thing", _Payload)


def test_register_rejects_a_kind_that_collides_with_a_schema_only_name() -> None:
    registry = StreamPartRegistry()
    registry.register_schema_only("thing", _Payload)
    with pytest.raises(DuplicateStreamPartError):
        registry.register("data-thing", _Payload)


def test_register_rejects_a_kind_without_the_data_prefix() -> None:
    registry = StreamPartRegistry()
    with pytest.raises(InvalidStreamPartNameError):
        registry.register("thing", _Payload)


def test_register_rejects_a_kind_that_is_not_an_identifier() -> None:
    registry = StreamPartRegistry()
    with pytest.raises(InvalidStreamPartNameError):
        registry.register("data-two words", _Payload)


def test_register_accepts_a_namespaced_kind() -> None:
    registry = StreamPartRegistry()
    registry.register("data-other.gene-view", _Payload)
    assert registry.kinds() == frozenset({"data-other.gene-view"})


def test_core_and_strategy_registrations_are_disjoint() -> None:
    core = StreamPartRegistry()
    register_core_stream_parts(core)
    strategy = StreamPartRegistry()
    register_strategy_stream_parts(strategy)
    core_names = {entry.schema_name for entry in core.entries()}
    strategy_names = {entry.schema_name for entry in strategy.entries()}
    assert core_names & strategy_names == set()


def test_registered_set_matches_the_pinned_schema_names() -> None:
    registry = _full_registry()
    assert {entry.schema_name for entry in registry.entries()} == PINNED_SCHEMA_NAMES


def test_registered_kinds_match_the_pinned_kinds() -> None:
    registry = _full_registry()
    assert registry.kinds() == PINNED_CORE_KINDS | PINNED_STRATEGY_KINDS


def test_core_registers_the_runtime_kinds() -> None:
    registry = StreamPartRegistry()
    register_core_stream_parts(registry)
    assert registry.kinds() == PINNED_CORE_KINDS


def test_strategy_registers_the_science_kinds() -> None:
    registry = StreamPartRegistry()
    register_strategy_stream_parts(registry)
    assert registry.kinds() == PINNED_STRATEGY_KINDS


def test_entries_are_ordered_by_schema_name() -> None:
    registry = StreamPartRegistry()
    registry.register("data-zeta", _Payload)
    registry.register("data-alpha", _Payload)
    assert [entry.schema_name for entry in registry.entries()] == ["alpha", "zeta"]


def test_schema_index_model_carries_one_optional_field_per_entry() -> None:
    registry = _full_registry()
    index = registry.schema_index_model()
    assert set(index.model_fields) == PINNED_SCHEMA_NAMES
    assert index().model_dump(exclude_none=True) == {}


def test_openapi_schema_exposes_every_registered_payload() -> None:
    spec = create_app().openapi()
    schemas = spec["components"]["schemas"]
    index = schemas["StreamPartsSchemaIndex"]["properties"]
    registry = _full_registry()
    for entry in registry.entries():
        assert to_camel(entry.schema_name) in index, entry.schema_name
        assert entry.model.__name__ in schemas, entry.model.__name__
