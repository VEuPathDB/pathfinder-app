from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ErrorKind = Literal["missing_required", "unknown_param", "type_error", "other"]
ToolStatus = Literal["started", "completed", "failed", "denied"]


class Chunk(BaseModel):
    """A single AI-SDK chunk as emitted by the pipeline. Envelope-level
    fields only; rich payloads stay in ``data`` for on-demand typed parsing."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    type: str = ""
    message_id: str | None = Field(default=None, alias="messageId")
    error_text: str | None = Field(default=None, alias="errorText")
    delta: str | None = None
    tool_call_id: str | None = Field(default=None, alias="toolCallId")
    tool_name: str | None = Field(default=None, alias="toolName")
    approval_id: str | None = Field(default=None, alias="approvalId")
    input: dict[str, Any] | None = None
    output: Any = None
    data: dict[str, Any] | None = None
    transient: bool = False


class SubAgentCallData(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    phase: str = ""
    state: str = ""
    sub_agent: str = Field(default="", alias="subAgent")
    tokens: int = 0
    cost_usd: str = Field(default="0", alias="costUsd")
    model_id: str = Field(default="", alias="modelId")
    summary: str = ""
    succeeded: bool | None = None
    tool_call_id: str | None = Field(default=None, alias="toolCallId")


class SubAgentStepData(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @field_validator("tool_name", "kind", "state", mode="before")
    @classmethod
    def _absent_is_empty(cls, value: object) -> object:
        return "" if value is None else value

    args: dict[str, Any] | None = None
    kind: str = ""
    text: str | None = None
    state: str = ""
    # A text or reasoning step names no tool, so the wire sends null.
    tool_name: str = Field(default="", alias="toolName", validate_default=False)
    tool_call_id: str | None = Field(default=None, alias="toolCallId")
    result_summary: str | None = Field(default=None, alias="resultSummary")
    parent_tool_call_id: str | None = Field(default=None, alias="parentToolCallId")


def sub_agent_call_data(data: dict[str, Any] | None) -> SubAgentCallData | None:
    return None if data is None else SubAgentCallData.model_validate(data)


def sub_agent_step_data(data: dict[str, Any] | None) -> SubAgentStepData | None:
    return None if data is None else SubAgentStepData.model_validate(data)


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    search_name: str | None = None


class ConstraintProbe(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: str = ""
    label: str = ""
    requested_value: str = Field(default="", alias="requestedValue")
    source: str = ""


class GroundedConstraintProbe(BaseModel):
    model_config = ConfigDict(extra="ignore")
    constraint: ConstraintProbe = Field(default_factory=ConstraintProbe)
    status: str = ""


class LedgerConstraintsProbe(BaseModel):
    model_config = ConfigDict(extra="ignore")
    blocking: bool = False
    unmet_count: int = Field(default=0, alias="unmetCount")
    grounded: list[GroundedConstraintProbe] = Field(default_factory=list)


class DecodedError(BaseModel):
    kind: ErrorKind = "other"
    search_name: str | None = None
    param: str | None = None
    loc: list[str] | None = None
    message: str = ""


class CapturedToolCall(BaseModel):
    seq: int
    phase: str = ""
    sub_agent: str = ""
    tool: str = ""
    tool_call_id: str = ""
    parent_tool_call_id: str | None = None
    args: dict[str, Any] | None = None
    status: ToolStatus = "started"
    result: str | None = None
    errors: list[DecodedError] = Field(default_factory=list)
    started_ms: float | None = None
    ended_ms: float | None = None
    duration_ms: float | None = None


class SpanNode(BaseModel):
    id: str
    kind: Literal["turn", "phase", "tool"]
    label: str
    status: str = ""
    duration_ms: float | None = None
    tokens: int = 0
    cost_usd: float = 0.0
    children: list[SpanNode] = Field(default_factory=list)


class PhaseSnapshot(BaseModel):
    phase: str
    ledger: dict[str, Any] | None = None


class Anomaly(BaseModel):
    kind: str
    severity: Literal["info", "warning", "critical"] = "warning"
    message: str
    evidence: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class RunSummary(BaseModel):
    status: str = "ok"
    terminal_error: str | None = None
    tokens: int = 0
    cost_usd: float = 0.0
    tool_calls: int = 0
    failures: int = 0
    phases: list[str] = Field(default_factory=list)
    anomaly_count: int = 0
    loop_detected: bool = False
    conversation_id: str = ""
    turn_id: str = ""
    run_dir: str = ""


_PYDANTIC_TYPE_MAP: dict[str, ErrorKind] = {
    "missing": "missing_required",
    "dict_type": "type_error",
    "model_type": "type_error",
    "list_type": "type_error",
    "string_type": "type_error",
    "int_type": "type_error",
}

_FENCE_RE = re.compile(r"```json\s*(?P<body>.+?)```", re.DOTALL)
_MISSING_RE = re.compile(r"Missing required parameters:\s*(?P<params>[^\n\"}]+)")
_UNKNOWN_RE = re.compile(r"parameter '(?P<param>[^']+)' does not exist", re.IGNORECASE)
_ON_SEARCH_RE = re.compile(r"on '(?P<search>[^']+)'")


def _decode_pydantic_array(text: str) -> list[DecodedError]:
    match = _FENCE_RE.search(text)
    raw = match.group("body").strip() if match else text.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError, ValueError:
        return []
    if not isinstance(parsed, list):
        return []
    out: list[DecodedError] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        loc = [str(p) for p in item.get("loc", [])]
        out.append(
            DecodedError(
                kind=_PYDANTIC_TYPE_MAP.get(str(item.get("type", "")), "other"),
                param=loc[-1] if loc else None,
                loc=loc or None,
                message=str(item.get("msg", "")),
            )
        )
    return out


def _decode_app_object(text: str) -> list[DecodedError]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError, ValueError:
        return []
    if not isinstance(parsed, dict):
        return []
    message = str(parsed.get("message", ""))
    out: list[DecodedError] = []
    errors = (parsed.get("details") or {}).get("errors") or []
    for err in errors:
        ctx = err.get("context") or {} if isinstance(err, dict) else {}
        search = ctx.get("searchName")
        out.extend(
            DecodedError(
                kind="missing_required",
                search_name=search,
                param=str(param),
                message=message,
            )
            for param in ctx.get("missing") or []
        )
    if not out and message.startswith("Missing required parameters"):
        out.extend(
            DecodedError(kind="missing_required", param=param, message=message)
            for param in _split_missing(message)
        )
    return out


def _split_missing(message: str) -> list[str]:
    match = _MISSING_RE.search(message)
    if not match:
        return []
    return [p.strip() for p in match.group("params").split(",") if p.strip()]


def _decode_plain_text(text: str) -> list[DecodedError]:
    out: list[DecodedError] = []
    for line in text.splitlines():
        param_match = _UNKNOWN_RE.search(line)
        if param_match:
            search_match = _ON_SEARCH_RE.search(line)
            out.append(
                DecodedError(
                    kind="unknown_param",
                    search_name=search_match.group("search") if search_match else None,
                    param=param_match.group("param"),
                    message=line.strip(),
                )
            )
    if out:
        return out
    out.extend(
        DecodedError(kind="missing_required", param=param, message=text.strip())
        for param in _split_missing(text)
    )
    return out


def decode_errors(result_text: str | None) -> list[DecodedError]:
    """Normalize a tool failure string into structured errors. Handles the
    three real shapes: fenced pydantic arrays, app ``VALIDATION_ERROR``
    objects, and plain-text 'unknown keys' / 'missing required' messages.
    Best-effort; never raises."""

    if not result_text:
        return []
    text = result_text.strip()
    if "```json" in text or text.startswith("["):
        decoded = _decode_pydantic_array(text)
        if decoded:
            return decoded
    if text.startswith("{"):
        decoded = _decode_app_object(text)
        if decoded:
            return decoded
    return _decode_plain_text(text)
