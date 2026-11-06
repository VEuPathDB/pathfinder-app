from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from pathfinder.devtools.capture import RunCapture
from pathfinder.devtools.inspector import (
    load_tool_calls,
    render_anomalies,
    render_diff,
    render_failures,
    render_llm,
    render_tool,
)

_CATCH22_MISSING = (
    '{"ok": false, "code": "VALIDATION_ERROR", '
    '"message": "Missing required parameters: document_type", '
    '"details": {"errors": [{"context": {"searchName": "GenesByText", '
    '"missing": ["document_type"]}}]}}'
)
_CATCH22_UNKNOWN = (
    "One or more planned step parameters reference unknown keys:\n"
    "  - on 'GenesByText': parameter 'document_type' does not exist. "
    "Valid params: ['text_expression', 'text_fields']"
)


def _catch22_run(tmp_path: Path) -> Path:
    cap = RunCapture(
        conversation_id=uuid4(), turn_id=uuid4(), run_dir=tmp_path, quiet=True
    )

    async def go() -> None:
        await cap.write(
            {
                "type": "data-sub-agent-call",
                "data": {
                    "phase": "planning",
                    "subAgent": "build_plan",
                    "state": "started",
                    "toolCallId": "p1",
                },
            }
        )
        for i, result in enumerate((_CATCH22_MISSING, _CATCH22_UNKNOWN), start=1):
            await cap.write(
                {
                    "type": "data-sub-agent-step",
                    "data": {
                        "toolName": "create_plan",
                        "toolCallId": f"c{i}",
                        "parentToolCallId": "p1",
                        "state": "started",
                        "args": {"steps": [{"parameters": {}}]},
                    },
                }
            )
            await cap.write(
                {
                    "type": "data-sub-agent-step",
                    "data": {
                        "toolName": "create_plan",
                        "toolCallId": f"c{i}",
                        "parentToolCallId": "p1",
                        "state": "failed",
                        "resultSummary": result,
                    },
                }
            )

    asyncio.run(go())
    return cap.flush()


def test_load_tool_calls_roundtrips(tmp_path: Path) -> None:
    run = _catch22_run(tmp_path)
    calls = load_tool_calls(run)
    assert len(calls) == 2
    assert all(c.tool == "create_plan" for c in calls)


def test_render_failures_correlates_args_and_errors(tmp_path: Path) -> None:
    run = _catch22_run(tmp_path)
    out = render_failures(run)
    assert "create_plan" in out
    assert "document_type" in out
    assert "missing_required" in out
    assert "unknown_param" in out


def test_render_anomalies_surfaces_catch22(tmp_path: Path) -> None:
    run = _catch22_run(tmp_path)
    out = render_anomalies(run)
    assert "validation_catch_22" in out
    assert "document_type" in out


def test_render_tool_shows_each_attempt(tmp_path: Path) -> None:
    run = _catch22_run(tmp_path)
    out = render_tool(run, "create_plan")
    assert out.count("attempt") >= 2 or out.count("create_plan") >= 2


def test_render_diff_flags_divergence(tmp_path: Path) -> None:
    run_a = _catch22_run(tmp_path / "a")
    cap = RunCapture(
        conversation_id=uuid4(), turn_id=uuid4(), run_dir=tmp_path / "b", quiet=True
    )

    async def go() -> None:
        await cap.write(
            {
                "type": "data-sub-agent-call",
                "data": {
                    "phase": "planning",
                    "subAgent": "build_plan",
                    "state": "started",
                    "toolCallId": "p1",
                },
            }
        )
        await cap.write(
            {
                "type": "data-sub-agent-step",
                "data": {
                    "toolName": "create_plan",
                    "toolCallId": "c1",
                    "parentToolCallId": "p1",
                    "state": "started",
                },
            }
        )
        await cap.write(
            {
                "type": "data-sub-agent-step",
                "data": {
                    "toolName": "create_plan",
                    "toolCallId": "c1",
                    "parentToolCallId": "p1",
                    "state": "completed",
                    "resultSummary": "ok",
                },
            }
        )

    asyncio.run(go())
    run_b = cap.flush()
    out = render_diff(run_a, run_b)
    assert "create_plan" in out


def test_render_llm_names_each_retry(tmp_path: Path) -> None:
    (tmp_path / "llm").mkdir()
    request = {
        "model": "openai:gpt-5.6-luna",
        "messages": [
            {
                "parts": [
                    {
                        "part_kind": "tool-return",
                        "tool_name": "set_criterion",
                        "content": "Name another search.",
                        "outcome": "retried",
                    },
                    {
                        "part_kind": "retry-feedback",
                        "content": "Please return text.",
                    },
                ]
            }
        ],
    }
    (tmp_path / "llm" / "01-frame-request.json").write_text(json.dumps(request))

    lines = render_llm(tmp_path, None).splitlines()

    assert lines[1:] == [
        "  [retry set_criterion] Name another search.",
        "  [retry] Please return text.",
    ]
