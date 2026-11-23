from __future__ import annotations

import json
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from strategist.domain.account_datasets import (
    UPLOAD_WORDS,
    StudyNames,
    account_datasets_in,
    is_account_dataset,
    names_any,
    scrubbed,
)

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
UPLOAD_BLOCK: Final = f"This part names {UPLOAD_WORDS} and is not shared."

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
    id: str | None = None
    tool_call_id: str | None = Field(default=None, alias="toolCallId")
    tool_name: str | None = Field(default=None, alias="toolName")
    delta: str | None = None

    def block(self) -> tuple[str, str] | None:
        if self.delta is None or self.id is None or self.tool_call_id is not None:
            return None
        return self.type.removesuffix("-delta"), self.id


class _Carrier(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: StudyNames = Field(default_factory=StudyNames)
    input: StudyNames = Field(default_factory=StudyNames)
    output: StudyNames = Field(default_factory=StudyNames)

    @field_validator("data", "input", "output", mode="before")
    @classmethod
    def _an_object_or_nothing(cls, value: JsonValue) -> JsonValue:
        match value:
            case dict():
                return value
            case _:
                return {}

    def marks(self) -> set[str]:
        return self.data.marks() | self.input.marks() | self.output.marks()


def _names(chunk: dict[str, Any], marks: set[str]) -> bool:
    return names_any(json.dumps(chunk), marks)


def _upload_marks(chunks: list[dict[str, Any]], read: list[_ToolChunk]) -> set[str]:
    marks = account_datasets_in(json.dumps(chunks))
    carriers = [_Carrier.model_validate(chunk) for chunk in chunks]
    while True:
        calls = {
            shape.tool_call_id
            for raw, shape in zip(chunks, read, strict=True)
            if shape.tool_call_id is not None and _names(raw, marks)
        }
        found = marks.union(
            *(
                carrier.marks()
                for raw, shape, carrier in zip(chunks, read, carriers, strict=True)
                if (shape.tool_call_id is not None and shape.tool_call_id in calls)
                or (
                    shape.type == _ANALYSIS_STATE
                    and is_account_dataset(carrier.data.dataset_id)
                )
            )
        )
        if found == marks:
            return marks
        marks = found


def _tainted_blocks(read: list[_ToolChunk], marks: set[str]) -> set[tuple[str, str]]:
    texts: dict[tuple[str, str], str] = {}
    for shape in read:
        block = shape.block()
        if block is not None and shape.delta is not None:
            texts[block] = texts.get(block, "") + shape.delta
    return {block for block, text in texts.items() if names_any(text, marks)}


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
    tainted = _tainted_blocks(read, marks)
    started: set[tuple[str, str]] = set()
    shown: list[tuple[int, dict[str, Any]]] = []
    for position, (raw, shape) in enumerate(zip(chunks, read, strict=True)):
        block = shape.block()
        if shape.type == _RECALLED_MEMORIES:
            shown.append((position, {**raw, "data": {"memories": []}}))
        elif shape.tool_call_id in calls:
            shown.append((position, _hidden(raw, shape.type)))
        elif block is not None and block in tainted:
            line = "" if block in started else UPLOAD_BLOCK
            started.add(block)
            shown.append((position, {**raw, "delta": line}))
        elif not _names(raw, marks):
            shown.append((position, raw))
        elif not shape.type.startswith(_DATA_PART):
            shown.append(
                (position, {key: scrubbed(value, marks) for key, value in raw.items()})
            )
    return shown


def without_owner_reads(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [chunk for _, chunk in shown_with_positions(chunks)]


def _hidden(chunk: dict[str, Any], kind: str) -> dict[str, Any]:
    named = {field: chunk[field] for field in _NAMING_FIELDS if field in chunk}
    return {**named, **_PLACEHOLDERS.get(kind, {})}
