from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

OWNER_READ_TOOLS: Final = frozenset(
    {
        "read_my_strategies",
        "list_my_threads",
        "read_my_thread",
        "read_gene_set",
        "search_memory",
        "list_control_sets",
        "read_control_set",
        "use_control_set",
        "list_gene_sets",
        "read_gene_ids_from_gene_set",
        "list_saved_strategies",
        "list_audit_runs",
        "read_audit_run",
        "list_audit_findings",
        "read_audit_findings",
        "review_audit_run",
        "get_download_url",
    }
)

_RECALLED_MEMORIES: Final = "data-memory-retrieved"

NOT_SHARED: Final = "Not shared: this read the owner's account."

_CALL_KINDS: Final = frozenset(
    {"tool-input-start", "tool-input-available", "tool-input-error"}
)
_NAMING_FIELDS: Final[tuple[str, ...]] = (
    "type",
    "toolCallId",
    "toolName",
    "approvalId",
)
_PLACEHOLDERS: Final[dict[str, dict[str, Any]]] = {
    "tool-input-delta": {"inputTextDelta": ""},
    "tool-input-available": {"input": {}},
    "tool-input-error": {"input": {}, "errorText": NOT_SHARED},
    "tool-output-available": {"output": NOT_SHARED},
    "tool-output-error": {"errorText": NOT_SHARED},
}


class _ToolChunk(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str = ""
    tool_call_id: str | None = Field(default=None, alias="toolCallId")
    tool_name: str | None = Field(default=None, alias="toolName")


def without_owner_reads(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    read = [_ToolChunk.model_validate(chunk) for chunk in chunks]
    calls = {
        chunk.tool_call_id
        for chunk in read
        if chunk.type in _CALL_KINDS and chunk.tool_name in OWNER_READ_TOOLS
    }
    return [
        {**raw, "data": {"memories": []}}
        if shape.type == _RECALLED_MEMORIES
        else _hidden(raw, shape.type)
        if shape.tool_call_id in calls
        else raw
        for raw, shape in zip(chunks, read, strict=True)
    ]


def _hidden(chunk: dict[str, Any], kind: str) -> dict[str, Any]:
    named = {field: chunk[field] for field in _NAMING_FIELDS if field in chunk}
    return {**named, **_PLACEHOLDERS.get(kind, {})}
