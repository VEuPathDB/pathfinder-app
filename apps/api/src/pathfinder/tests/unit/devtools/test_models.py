from __future__ import annotations

from pathfinder.devtools.models import (
    Chunk,
    SubAgentStepData,
    decode_errors,
    sub_agent_call_data,
    sub_agent_step_data,
)
from pathfinder.tests._support.models import DEFAULT_MODEL

PYDANTIC_FAILURE = """9 validation errors:
```json
[
  {
    "type": "dict_type",
    "loc": ["steps", 0, "parameters", "text_search_organism"],
    "msg": "Input should be an object",
    "input": ["Aedes aegypti LVP_AGWG"]
  }
]
```"""

APP_MISSING = (
    '{"ok": false, "code": "VALIDATION_ERROR", '
    '"message": "Missing required parameters: document_type", '
    '"details": {"errors": [{"context": {"recordType": "transcript", '
    '"searchName": "GenesByText", "missing": ["document_type"]}}]}}'
)

UNKNOWN_KEYS = (
    "One or more planned step parameters reference unknown keys:\n"
    "  - on 'GenesByText': parameter 'document_type' does not exist. "
    "Did you mean: ['text_fields']? "
    "Valid params: ['text_expression', 'text_fields', 'text_search_organism']"
)


def test_decode_pydantic_style_extracts_loc_and_type() -> None:
    errs = decode_errors(PYDANTIC_FAILURE)
    assert len(errs) == 1
    e = errs[0]
    assert e.kind == "type_error"
    assert e.param == "text_search_organism"
    assert e.loc == ["steps", "0", "parameters", "text_search_organism"]
    assert "object" in e.message


def test_decode_app_missing_required_extracts_param_and_search() -> None:
    errs = decode_errors(APP_MISSING)
    missing = [e for e in errs if e.kind == "missing_required"]
    assert any(
        e.param == "document_type" and e.search_name == "GenesByText" for e in missing
    )


def test_decode_unknown_keys_extracts_param_and_search() -> None:
    errs = decode_errors(UNKNOWN_KEYS)
    unknown = [e for e in errs if e.kind == "unknown_param"]
    assert any(
        e.param == "document_type" and e.search_name == "GenesByText" for e in unknown
    )


def test_decode_garbage_never_raises() -> None:
    assert decode_errors("not json at all, just prose") == []
    assert decode_errors("") == []


def test_chunk_parses_envelope_fields() -> None:
    c = Chunk.model_validate(
        {
            "type": "tool-approval-request",
            "approvalId": "call_x",
            "toolCallId": "call_x",
        }
    )
    assert c.type == "tool-approval-request"
    assert c.tool_call_id == "call_x"
    assert c.approval_id == "call_x"


def test_sub_agent_call_data_parses() -> None:
    d = sub_agent_call_data(
        {
            "phase": "scoping",
            "state": "started",
            "subAgent": "scope_problem",
            "tokens": 5215,
            "costUsd": "0.0024",
            "modelId": DEFAULT_MODEL,
            "toolCallId": "call_dj",
        }
    )
    assert d is not None
    assert d.phase == "scoping"
    assert d.sub_agent == "scope_problem"
    assert d.tokens == 5215
    assert d.tool_call_id == "call_dj"


def test_sub_agent_step_data_parses_parent_and_args() -> None:
    d = sub_agent_step_data(
        {
            "args": {"thought": "x"},
            "kind": "tool",
            "state": "started",
            "toolName": "think",
            "toolCallId": "call_6r",
            "parentToolCallId": "call_dj",
        }
    )
    assert d is not None
    assert d.tool_name == "think"
    assert d.parent_tool_call_id == "call_dj"
    assert d.args == {"thought": "x"}


def test_a_thinking_step_carries_no_tool_name() -> None:
    # A text or reasoning step has no tool, so the wire sends toolName null.
    data = SubAgentStepData.model_validate(
        {
            "kind": "text",
            "state": "completed",
            "text": "weighing options",
            "toolName": None,
            "toolCallId": None,
            "args": None,
        },
    )

    assert data.tool_name == ""
    assert data.kind == "text"
