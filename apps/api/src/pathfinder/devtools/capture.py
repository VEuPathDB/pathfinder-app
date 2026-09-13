from __future__ import annotations

import json
import logging
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from itertools import count
from pathlib import Path
from typing import Any
from uuid import UUID

from pathfinder.devtools.diagnosis import diagnose
from pathfinder.devtools.models import (
    Anomaly,
    CapturedToolCall,
    Chunk,
    PhaseSnapshot,
    RunSummary,
    SpanNode,
    ToolStatus,
    decode_errors,
    sub_agent_call_data,
    sub_agent_step_data,
)

LOOP_THRESHOLD = 5
RESULT_CLIP = 140
# The model's terminal call. The reply it carries is the transcript's own
# section, so a call that answered draws no row; one that failed is a retry of
# the output itself, which every artifact shows.
OUTPUT_TOOL = "final_result"
_ARTIFACT_SUBDIRS = ("tools", "state", "errors", "wdk")
_ARTIFACT_FILES = (
    "events.jsonl",
    "summary.json",
    "diagnosis.json",
    "tree.json",
    "tree.txt",
    "transcript.md",
)


def reset_run_dir(run_dir: Path) -> None:
    """Clear prior artifacts so a re-used ``--run-dir`` never mixes two runs.
    Removes only the known artifact subdirs and top-level files; anything else
    in the directory is left untouched. Re-creates the (empty) directory."""

    run_dir = Path(run_dir)
    for sub in _ARTIFACT_SUBDIRS:
        shutil.rmtree(run_dir / sub, ignore_errors=True)
    for name in _ARTIFACT_FILES:
        (run_dir / name).unlink(missing_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)


_SILENT_TYPES = {
    "data-turn-usage",
    "data-lead-usage",
    "data-turn-status",
    "start-step",
    "finish-step",
    "finish",
    "done",
    "text-start",
    "text-end",
    "tool-input-start",
    "tool-input-delta",
    "tool-input-available",
    "message-metadata",
    "data-scratchpad-updated",
    "source-url",
}


def _as_text(value: object) -> str:
    """One tool result, as the transcript prints it."""
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def _clip(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= RESULT_CLIP else flat[: RESULT_CLIP - 1] + "…"


class _TracebackHandler(logging.Handler):
    def __init__(self, errors_dir: Path) -> None:
        super().__init__(level=logging.ERROR)
        self._dir = errors_dir
        self._seq = count(1)

    def emit(self, record: logging.LogRecord) -> None:
        field_tb = record.__dict__.get("traceback")
        if record.exc_info is None and not field_tb and record.levelno < logging.ERROR:
            return
        self._dir.mkdir(parents=True, exist_ok=True)
        name = f"{next(self._seq):02d}-{record.name.replace('.', '_')}.txt"
        parts = [record.getMessage(), self.format(record)]
        if isinstance(field_tb, str):
            parts.append(field_tb)
        (self._dir / name).write_text("\n\n".join(p for p in parts if p))


@contextmanager
def capture_tracebacks(run_dir: Path) -> Iterator[None]:
    """Capture every logged exception (records with ``exc_info``) into
    ``<run_dir>/errors/`` for the duration of the block. In-process only —
    the HTTP path never sees these Python stacks."""

    handler = _TracebackHandler(run_dir / "errors")
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield
    finally:
        root.removeHandler(handler)


class RunCapture:
    """Chat writer that captures one turn into a full-fidelity run directory
    while printing a clean compact trace. Implements the ``ChatWriter``
    protocol (``write``/``conversation_id``/``turn_id``)."""

    def __init__(
        self,
        *,
        conversation_id: UUID,
        turn_id: UUID,
        run_dir: Path,
        quiet: bool = False,
    ) -> None:
        self.conversation_id = conversation_id
        self.turn_id = turn_id
        self.run_dir = Path(run_dir)
        self.quiet = quiet
        self._ids = count(1)
        self._events: list[dict[str, Any]] = []
        self._calls: dict[str, CapturedToolCall] = {}
        self._seq = count(1)
        self._phase_by_call: dict[str, str] = {}
        self._subagent_by_call: dict[str, str] = {}
        self._tool_name_by_call: dict[str, str] = {}
        self._tool_args_by_call: dict[str, dict[str, Any]] = {}
        self._announced_calls: set[str] = set()
        self._durable_tasks: list[tuple[str, str]] = []
        self._current_phase = ""
        self._ledger_by_phase: dict[str, dict[str, Any]] = {}
        self._tokens = 0
        self._cost = 0.0
        self._has_error = False
        self._reply_parts: list[str] = []
        self._terminal_error: str | None = None
        self._fail_counts: dict[str, int] = {}
        self._looped_tools: set[str] = set()
        self._loop = False
        self._pending: tuple[str, str] | None = None

    async def write(self, chunk: dict[str, Any]) -> int:
        event_id = next(self._ids)
        self._events.append(chunk)
        env = Chunk.model_validate(chunk)
        self._accumulate(env)
        if not self.quiet:
            line = self._render(env)
            if line is not None:
                print(line)
        return event_id

    def _accumulate(self, env: Chunk) -> None:
        handler = {
            "data-sub-agent-call": self._on_call,
            "data-sub-agent-step": self._on_step,
            "data-turn-usage": self._on_turn_usage,
            "data-ledger-update": self._on_ledger,
            "tool-input-available": self._on_tool_input,
            "tool-output-available": self._on_tool_output,
            "tool-output-error": self._on_tool_output_error,
            "tool-output-denied": self._on_tool_denied,
            "tool-approval-request": self._on_approval,
            "data-background-task-started": self._on_durable_task,
            "error": self._on_error,
            "text-delta": self._on_text,
        }.get(env.type)
        if env.type == "start":
            self._pending = None
            self._durable_tasks = []
        if handler is not None:
            handler(env)

    def _on_call(self, env: Chunk) -> None:
        data = sub_agent_call_data(env.data)
        if data is None or not data.tool_call_id:
            return
        self._phase_by_call[data.tool_call_id] = data.phase
        self._subagent_by_call[data.tool_call_id] = data.sub_agent
        if data.phase:
            self._current_phase = data.phase

    def _on_step(self, env: Chunk) -> None:
        data = sub_agent_step_data(env.data)
        if data is None or not data.tool_call_id:
            return
        tcid = data.tool_call_id
        parent = data.parent_tool_call_id
        phase = self._phase_by_call.get(parent or "", self._current_phase)
        sub_agent = self._subagent_by_call.get(parent or "", "")
        if data.state == "started":
            self._calls[tcid] = CapturedToolCall(
                seq=next(self._seq),
                phase=phase,
                sub_agent=sub_agent,
                tool=data.tool_name,
                tool_call_id=tcid,
                parent_tool_call_id=parent,
                args=data.args,
                status="started",
                started_ms=time.perf_counter() * 1000.0,
            )
            return
        call = self._calls.get(tcid)
        if call is None:
            return
        call.ended_ms = time.perf_counter() * 1000.0
        if call.started_ms is not None:
            call.duration_ms = call.ended_ms - call.started_ms
        if data.state == "completed":
            call.status = "completed"
            call.result = data.result_summary
            self._fail_counts.pop(call.tool, None)
        elif data.state == "failed":
            call.status = "failed"
            call.result = data.result_summary
            call.errors = decode_errors(data.result_summary)
            self._note_failure(call.tool)
        elif data.state == "denied":
            # The user refused the call. The tool did not fail, so the loop
            # counter stays where it is.
            call.status = "denied"
            call.result = data.result_summary

    def _note_failure(self, tool: str) -> None:
        self._fail_counts[tool] = self._fail_counts.get(tool, 0) + 1
        if self._fail_counts[tool] >= LOOP_THRESHOLD and tool not in self._looped_tools:
            self._loop = True
            self._looped_tools.add(tool)
            if not self.quiet:
                print(f"⚠ loop: {tool} failed {self._fail_counts[tool]} times")

    def _on_turn_usage(self, env: Chunk) -> None:
        data = env.data or {}
        self._tokens = max(self._tokens, int(data.get("totalTokens", 0) or 0))
        self._cost = max(self._cost, float(data.get("costUsd", 0) or 0))

    def _on_ledger(self, env: Chunk) -> None:
        if env.data is not None:
            self._ledger_by_phase[self._current_phase or "turn"] = env.data

    def _on_tool_input(self, env: Chunk) -> None:
        if not env.tool_call_id:
            return
        self._announced_calls.add(env.tool_call_id)
        if env.tool_name:
            self._tool_name_by_call[env.tool_call_id] = env.tool_name
        if env.input is not None:
            self._tool_args_by_call[env.tool_call_id] = env.input
        if env.tool_call_id in self._calls:
            return
        # The turn's own call. A sub-agent's inner call runs outside the
        # adapter and arrives as a step instead.
        self._calls[env.tool_call_id] = CapturedToolCall(
            seq=next(self._seq),
            tool=env.tool_name or self._tool_name_by_call.get(env.tool_call_id, ""),
            tool_call_id=env.tool_call_id,
            args=env.input,
            status="started",
            started_ms=time.perf_counter() * 1000.0,
        )

    def _settle(self, env: Chunk, status: ToolStatus, result: str | None) -> None:
        """Close the turn's own call the way a sub-agent step closes its own."""
        call = self._calls.get(env.tool_call_id or "")
        if call is None:
            return
        call.ended_ms = time.perf_counter() * 1000.0
        if call.started_ms is not None:
            call.duration_ms = call.ended_ms - call.started_ms
        call.status = status
        call.result = result
        if status == "failed":
            call.errors = decode_errors(result)
            self._note_failure(call.tool)
        elif status == "completed":
            self._fail_counts.pop(call.tool, None)

    def _on_tool_output(self, env: Chunk) -> None:
        self._settle(env, "completed", _as_text(env.output))

    def _on_tool_output_error(self, env: Chunk) -> None:
        # A tool the model can answer is not a failed run: the row carries the
        # failure and the run's status stays with the terminal error.
        self._settle(env, "failed", env.error_text)

    def _on_tool_denied(self, env: Chunk) -> None:
        self._settle(env, "denied", "the user denied the call")

    def _on_durable_task(self, env: Chunk) -> None:
        data = env.data or {}
        task_id = data.get("taskId")
        if task_id:
            self._durable_tasks.append(
                (str(task_id), str(data.get("toolName") or "?")),
            )

    def _on_approval(self, env: Chunk) -> None:
        if not env.tool_call_id:
            return
        name = self._tool_name_by_call.get(env.tool_call_id, "?")
        self._pending = (name, env.tool_call_id)

    def _on_error(self, env: Chunk) -> None:
        self._has_error = True
        self._terminal_error = env.error_text

    def _on_text(self, env: Chunk) -> None:
        if env.delta:
            self._reply_parts.append(env.delta)

    def assistant_text(self) -> str:
        """The reply the user actually saw, reassembled from text deltas.

        The ``silent_*`` detectors read it: an issue the Lead explained in
        prose is not silent, and the ledger's structured fields cannot show
        that.
        """
        return "".join(self._reply_parts)

    def _render(self, env: Chunk) -> str | None:
        if env.type == "data-sub-agent-call":
            d = sub_agent_call_data(env.data)
            return None if d is None else f"[{d.phase:9}] {d.sub_agent:18} {d.state}"
        if env.type == "data-sub-agent-step":
            return self._render_step(env)
        simple = {
            "error": f"✖ ERROR  {env.error_text or ''}",
            "tool-output-error": f"✖ tool error  {env.error_text or ''}",
            "text-delta": env.delta or "",
            "tool-approval-request": (
                f"⏸ approval gate: {self._pending[0] if self._pending else '?'}"
            ),
        }
        if env.type in simple:
            return simple[env.type]
        return None if env.type in _SILENT_TYPES else f"· {env.type}"

    def _render_step(self, env: Chunk) -> str | None:
        d = sub_agent_step_data(env.data)
        if d is None or d.state == "started":
            return None
        tag = "FAILED" if d.state == "failed" else d.state.upper()
        tail = f"  {_clip(d.result_summary)}" if d.result_summary else ""
        return f"[{self._current_phase:9}] · {d.tool_name:18} {tag}{tail}"

    @property
    def pending_approval(self) -> tuple[str, str] | None:
        return self._pending

    @property
    def durable_tasks(self) -> list[tuple[str, str]]:
        """Every task this turn handed to the worker, in the order it did."""
        return list(self._durable_tasks)

    @property
    def tool_args_by_call(self) -> dict[str, dict[str, Any]]:
        return self._tool_args_by_call

    @property
    def has_error(self) -> bool:
        return self._has_error

    def tool_calls(self) -> list[CapturedToolCall]:
        return sorted(self._calls.values(), key=lambda c: c.seq)

    def rendered_calls(self) -> list[CapturedToolCall]:
        """The calls an artifact draws. A terminal call that answered is the
        reply, which the transcript prints on its own."""
        return [
            call
            for call in self.tool_calls()
            if not (call.tool == OUTPUT_TOOL and call.status == "completed")
        ]

    def phases(self) -> list[str]:
        seen: list[str] = []
        for call in self.tool_calls():
            if call.phase and call.phase not in seen:
                seen.append(call.phase)
        return seen

    def snapshots(self) -> list[PhaseSnapshot]:
        return [
            PhaseSnapshot(
                phase=phase,
                ledger=self._ledger_by_phase.get(phase),
            )
            for phase in self.phases() or list(self._ledger_by_phase)
        ]

    def tree(self) -> SpanNode:
        calls = self.rendered_calls()
        phase_nodes: dict[str, SpanNode] = {}
        order: list[str] = []
        for call in calls:
            key = call.phase or "lead"
            if key not in phase_nodes:
                phase_nodes[key] = SpanNode(id=key, kind="phase", label=key)
                order.append(key)
            phase_nodes[key].children.append(
                SpanNode(
                    id=call.tool_call_id,
                    kind="tool",
                    label=call.tool,
                    status=call.status,
                    duration_ms=call.duration_ms,
                )
            )
        return SpanNode(
            id=str(self.turn_id),
            kind="turn",
            label="turn",
            status="error" if self._has_error else "ok",
            tokens=self._tokens,
            cost_usd=self._cost,
            children=[phase_nodes[k] for k in order],
        )

    def anomalies(self) -> list[Anomaly]:
        return diagnose(
            self.tool_calls(),
            self._ledger_by_phase,
            self.summary(),
            self.assistant_text(),
        )

    def counted_calls(self) -> set[str]:
        """Every tool call the event log announces, whatever the assistant.

        A one-agent turn announces its own with ``tool-input-available``; a
        Lead announces its dispatches that way and its inner calls as steps.
        """
        settled = {
            call.tool_call_id for call in self.tool_calls() if call.status != "started"
        }
        return self._announced_calls | settled

    def summary(self) -> RunSummary:
        calls = self.tool_calls()
        return RunSummary(
            status="error" if self._has_error else "ok",
            terminal_error=self._terminal_error,
            tokens=self._tokens,
            cost_usd=self._cost,
            tool_calls=len(self.counted_calls()),
            failures=len([c for c in calls if c.status == "failed"]),
            phases=self.phases(),
            loop_detected=self._loop,
            conversation_id=str(self.conversation_id),
            turn_id=str(self.turn_id),
            run_dir=str(self.run_dir),
        )

    def _render_tree_text(self, node: SpanNode, depth: int = 0) -> list[str]:
        pad = "  " * depth
        dur = f" {node.duration_ms:.0f}ms" if node.duration_ms else ""
        status = f" [{node.status}]" if node.status else ""
        lines = [f"{pad}{node.label}{status}{dur}"]
        for child in node.children:
            lines.extend(self._render_tree_text(child, depth + 1))
        return lines

    def _transcript(self) -> str:
        out = [f"# Turn {self.turn_id}", f"conversation: {self.conversation_id}", ""]
        for call in self.rendered_calls():
            out.append(f"- [{call.phase or 'lead'}] {call.tool} → {call.status}")
            if call.result:
                out.append(f"    {_clip(call.result)}")
        reply = self.assistant_text()
        if reply:
            out += ["", "## Reply", "", reply]
        return "\n".join(out) + "\n"

    def flush(self) -> Path:
        out = self.run_dir
        (out / "tools").mkdir(parents=True, exist_ok=True)
        (out / "state").mkdir(parents=True, exist_ok=True)
        with (out / "events.jsonl").open("w") as fh:
            for event in self._events:
                fh.write(json.dumps(event, separators=(",", ":")) + "\n")
        for call in self.rendered_calls():
            name = f"{call.seq:02d}-{call.tool or 'unknown'}.json"
            (out / "tools" / name).write_text(call.model_dump_json(indent=2))
        for snap in self.snapshots():
            (out / "state" / f"{snap.phase}.json").write_text(
                snap.model_dump_json(indent=2)
            )
        tree = self.tree()
        (out / "tree.json").write_text(tree.model_dump_json(indent=2))
        (out / "tree.txt").write_text("\n".join(self._render_tree_text(tree)) + "\n")
        anomalies = self.anomalies()
        (out / "diagnosis.json").write_text(
            json.dumps([a.model_dump() for a in anomalies], indent=2)
        )
        summary = self.summary()
        summary.anomaly_count = len(anomalies)
        (out / "summary.json").write_text(summary.model_dump_json(indent=2))
        (out / "transcript.md").write_text(self._transcript())
        return out
