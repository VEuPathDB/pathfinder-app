from __future__ import annotations

import json
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from strategist.domain.account_datasets import account_datasets_in, is_account_dataset

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
_ANALYSIS_STATE: Final = "data-eda.analysis-state"
_DATA_PART: Final = "data-"
_UPLOAD_WORDS: Final = "a private dataset"

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
    delta: str | None = None


class _StateIds(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dataset_id: str = Field(default="", alias="datasetId")
    study_id: str = Field(default="", alias="studyId")
    analysis_id: str = Field(default="", alias="analysisId")


class _StateChunk(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: _StateIds = Field(default_factory=_StateIds)


def _upload_marks(chunks: list[dict[str, Any]], read: list[_ToolChunk]) -> set[str]:
    marks = account_datasets_in(json.dumps(chunks))
    for raw, shape in zip(chunks, read, strict=True):
        if shape.type != _ANALYSIS_STATE:
            continue
        ids = _StateChunk.model_validate(raw).data
        if is_account_dataset(ids.dataset_id):
            marks |= {ids.study_id, ids.analysis_id} - {""}
    return marks


def _names(chunk: dict[str, Any], marks: set[str]) -> bool:
    text = json.dumps(chunk)
    return any(mark in text for mark in marks)


def _scrubbed(delta: str, marks: set[str]) -> str:
    for mark in sorted(marks, key=len, reverse=True):
        delta = delta.replace(mark, _UPLOAD_WORDS)
    return delta


def shown_with_positions(
    chunks: list[dict[str, Any]],
) -> list[tuple[int, dict[str, Any]]]:
    read = [_ToolChunk.model_validate(chunk) for chunk in chunks]
    marks = _upload_marks(chunks, read)
    calls = {
        chunk.tool_call_id
        for chunk in read
        if chunk.type in _CALL_KINDS and chunk.tool_name in OWNER_READ_TOOLS
    } | {
        shape.tool_call_id
        for raw, shape in zip(chunks, read, strict=True)
        if shape.tool_call_id is not None and _names(raw, marks)
    }
    shown: list[tuple[int, dict[str, Any]]] = []
    for position, (raw, shape) in enumerate(zip(chunks, read, strict=True)):
        if shape.type == _RECALLED_MEMORIES:
            shown.append((position, {**raw, "data": {"memories": []}}))
        elif shape.tool_call_id in calls:
            shown.append((position, _hidden(raw, shape.type)))
        elif not _names(raw, marks):
            shown.append((position, raw))
        elif shape.delta is not None:
            shown.append((position, {**raw, "delta": _scrubbed(shape.delta, marks)}))
        elif not shape.type.startswith(_DATA_PART):
            shown.append((position, raw))
    return shown


def without_owner_reads(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [chunk for _, chunk in shown_with_positions(chunks)]


def _hidden(chunk: dict[str, Any], kind: str) -> dict[str, Any]:
    named = {field: chunk[field] for field in _NAMING_FIELDS if field in chunk}
    return {**named, **_PLACEHOLDERS.get(kind, {})}
