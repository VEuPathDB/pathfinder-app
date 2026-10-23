from __future__ import annotations

import pytest
from assistant_core.conversation.stream_parts.registry import (
    DuplicateStreamPartError,
    StreamPartRegistry,
)
from pydantic import BaseModel

from pathfinder.assistants.audit.spec import build_audit_spec
from pathfinder.assistants.pathfinder_spec import build_pathfinder_spec
from pathfinder.transport.http.openapi import register_stream_parts_of


class _Other(BaseModel):
    value: str = ""


def test_the_start_card_both_assistants_emit_is_registered_once() -> None:
    registry = StreamPartRegistry()

    register_stream_parts_of((build_pathfinder_spec(), build_audit_spec()), registry)

    assert [e.kind for e in registry.entries() if e.kind == "data-audit-start"] == [
        "data-audit-start"
    ]


def test_another_payload_under_the_same_kind_is_refused() -> None:
    registry = StreamPartRegistry()
    registry.register("data-audit-start", _Other)

    with pytest.raises(DuplicateStreamPartError):
        register_stream_parts_of((build_audit_spec(),), registry)
