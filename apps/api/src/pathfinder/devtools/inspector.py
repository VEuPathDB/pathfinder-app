from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from pathfinder.devtools.models import Anomaly, CapturedToolCall

_ANOMALIES = TypeAdapter(list[Anomaly])


def load_tool_calls(run_dir: Path) -> list[CapturedToolCall]:
    tools_dir = run_dir / "tools"
    if not tools_dir.is_dir():
        return []
    calls = [
        CapturedToolCall.model_validate_json(p.read_text())
        for p in sorted(tools_dir.glob("*.json"))
    ]
    return sorted(calls, key=lambda c: c.seq)


def load_anomalies(run_dir: Path) -> list[Anomaly]:
    path = run_dir / "diagnosis.json"
    if not path.is_file():
        return []
    return _ANOMALIES.validate_json(path.read_text())


def _traceback_for(run_dir: Path, seq: int) -> str | None:
    matches = (
        sorted((run_dir / "errors").glob(f"{seq:02d}-*.txt"))
        if (run_dir / "errors").is_dir()
        else []
    )
    return matches[0].read_text() if matches else None


def _wdk_files(run_dir: Path) -> list[str]:
    wdk = run_dir / "wdk"
    return [p.name for p in sorted(wdk.glob("*.json"))] if wdk.is_dir() else []


def render_failures(run_dir: Path) -> str:
    failures = [c for c in load_tool_calls(run_dir) if c.status == "failed"]
    if not failures:
        return "No failed tool calls."
    blocks: list[str] = []
    for call in failures:
        lines = [f"#{call.seq:02d} [{call.phase}] {call.tool}  FAILED"]
        lines.append("  args: " + json.dumps(call.args, indent=2)[:2000])
        for err in call.errors:
            where = f" on {err.search_name}" if err.search_name else ""
            lines.append(
                f"  · {err.kind} {err.param or ''}{where}: {err.message[:200]}"
            )
        tb = _traceback_for(run_dir, call.seq)
        if tb:
            lines.append("  traceback:\n" + tb)
        blocks.append("\n".join(lines))
    wdk = _wdk_files(run_dir)
    if wdk:
        blocks.append("WDK round-trips captured: " + ", ".join(wdk))
    return "\n\n".join(blocks)


def render_tool(run_dir: Path, tool: str) -> str:
    attempts = [c for c in load_tool_calls(run_dir) if c.tool == tool]
    if not attempts:
        return f"No calls to {tool!r}."
    blocks: list[str] = []
    prev_args: dict[str, Any] | None = None
    for n, call in enumerate(attempts, start=1):
        lines = [f"attempt {n}  #{call.seq:02d}  {call.status}"]
        if call.args != prev_args:
            lines.append("  args changed: " + json.dumps(call.args)[:1500])
        else:
            lines.append("  args identical to previous attempt")
        if call.errors:
            lines.append(
                "  errors: " + "; ".join(f"{e.kind}:{e.param}" for e in call.errors)
            )
        prev_args = call.args
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def render_anomalies(run_dir: Path) -> str:
    anomalies = load_anomalies(run_dir)
    if not anomalies:
        return "No anomalies detected."
    blocks = [
        f"[{a.severity.upper()}] {a.kind}\n"
        f"  {a.message}\n"
        f"  evidence: {', '.join(a.evidence)}"
        for a in anomalies
    ]
    return "\n\n".join(blocks)


def render_tree(run_dir: Path) -> str:
    path = run_dir / "tree.txt"
    return path.read_text() if path.is_file() else "No tree.txt."


def _part_line(part: dict[str, Any]) -> str | None:
    content = str(part.get("content", ""))
    tool = part.get("tool_name") or ""
    formatters = {
        "system-prompt": lambda: f"  [system] {content[:1500]}",
        "user-prompt": lambda: f"  [user] {content[:800]}",
        "tool-return": lambda: f"  [tool-return {tool}] {content[:800]}",
        "retry-prompt": lambda: f"  [retry {tool}] {content[:800]}",
        "text": lambda: f"  [text] {content[:800]}",
        "thinking": lambda: f"  [thinking] {content[:400]}",
        "tool-call": lambda: (
            f"  [tool-call {tool}] {json.dumps(part.get('args'))[:600]}"
        ),
    }
    fmt = formatters.get(str(part.get("part_kind")))
    return fmt() if fmt is not None else None


def render_llm(run_dir: Path, role: str | None) -> str:
    llm_dir = run_dir / "llm"
    if not llm_dir.is_dir():
        return "No llm/ capture (run with --capture-llm)."
    blocks: list[str] = []
    for req_path in sorted(llm_dir.glob("*-request.json")):
        req = json.loads(req_path.read_text())
        if role is not None and req.get("role") != role:
            continue
        stem = req_path.name.removesuffix("-request.json")
        lines = [
            f"━━ {stem}  model={req.get('model')}  tools={len(req.get('tools', []))}"
        ]
        messages = req.get("messages", [])
        last = messages[-1] if messages else {}
        if isinstance(last, dict) and last.get("instructions"):
            lines.append(f"  [instructions] {str(last['instructions'])[:1500]}")
        for msg in messages:
            for part in msg.get("parts", []) if isinstance(msg, dict) else []:
                line = _part_line(part)
                if line is not None:
                    lines.append(line)
        resp_path = llm_dir / f"{stem}-response.json"
        if resp_path.is_file():
            resp = json.loads(resp_path.read_text())
            lines.append(f"  -> response (finish={resp.get('finishReason')}):")
            for part in resp.get("response", {}).get("parts", []):
                line = _part_line(part)
                if line is not None:
                    lines.append("  " + line)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) if blocks else "No matching LLM calls."


def _signature(calls: list[CapturedToolCall]) -> list[tuple[str, str]]:
    return [(c.tool, c.status) for c in calls]


def render_diff(run_a: Path, run_b: Path) -> str:
    sig_a = _signature(load_tool_calls(run_a))
    sig_b = _signature(load_tool_calls(run_b))
    lines = [
        f"A: {run_a.name}  ({len(sig_a)} calls)",
        f"B: {run_b.name}  ({len(sig_b)} calls)",
        "",
    ]
    for i in range(max(len(sig_a), len(sig_b))):
        a = sig_a[i] if i < len(sig_a) else None
        b = sig_b[i] if i < len(sig_b) else None
        marker = "  " if a == b else "≠ "
        lines.append(f"{marker}#{i + 1:02d}  A={a}  B={b}")
        if a != b:
            lines.append("  ^ divergence point")
            break
    return "\n".join(lines)
