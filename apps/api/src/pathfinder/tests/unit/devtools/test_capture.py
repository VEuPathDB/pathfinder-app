from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from uuid import uuid4

from assistant_core.platform.types import JSONObject
from pydantic import TypeAdapter

from pathfinder.devtools.capture import (
    LOOP_THRESHOLD,
    OUTPUT_TOOL,
    RunCapture,
    capture_tracebacks,
    reset_run_dir,
)
from pathfinder.platform.durable_worker import durable_call_refusal


def _write(cap: RunCapture, chunk: JSONObject) -> None:
    asyncio.run(cap.write(chunk))


def _call(phase: str, sub_agent: str, tcid: str, state: str) -> JSONObject:
    return {
        "type": "data-sub-agent-call",
        "data": {
            "phase": phase,
            "subAgent": sub_agent,
            "state": state,
            "toolCallId": tcid,
        },
    }


def _step(
    tool: str,
    tcid: str,
    parent: str,
    state: str,
    *,
    args: JSONObject | None = None,
    result: str | None = None,
) -> JSONObject:
    return {
        "type": "data-sub-agent-step",
        "data": {
            "toolName": tool,
            "toolCallId": tcid,
            "parentToolCallId": parent,
            "state": state,
            "args": args,
            "resultSummary": result,
        },
    }


def _new(tmp_path: Path) -> RunCapture:
    return RunCapture(
        conversation_id=uuid4(), turn_id=uuid4(), run_dir=tmp_path, quiet=True
    )


def test_tool_call_pairs_start_and_complete(tmp_path: Path) -> None:
    cap = _new(tmp_path)
    _write(cap, _step("think", "c1", "p1", "started", args={"thought": "x"}))
    _write(cap, _step("think", "c1", "p1", "completed", result="done"))
    calls = cap.tool_calls()
    assert len(calls) == 1
    assert calls[0].tool == "think"
    assert calls[0].status == "completed"
    assert calls[0].args == {"thought": "x"}
    assert calls[0].result == "done"


def test_failed_tool_call_decodes_errors(tmp_path: Path) -> None:
    cap = _new(tmp_path)
    _write(cap, _step("create_plan", "c2", "p1", "started", args={"steps": []}))
    _write(
        cap,
        _step(
            "create_plan",
            "c2",
            "p1",
            "failed",
            result='{"ok": false, "code": "VALIDATION_ERROR", '
            '"message": "Missing required parameters: document_type", '
            '"details": {"errors": [{"context": {"searchName": "GenesByText", '
            '"missing": ["document_type"]}}]}}',
        ),
    )
    call = cap.tool_calls()[0]
    assert call.status == "failed"
    assert any(
        e.param == "document_type" and e.kind == "missing_required" for e in call.errors
    )


def test_denied_tool_call_is_terminal_and_is_not_a_failure(tmp_path: Path) -> None:
    cap = _new(tmp_path)
    for i in range(LOOP_THRESHOLD):
        tcid = f"d{i}"
        _write(cap, _step("delete_step", tcid, "p1", "started", args={"stepId": "s2"}))
        _write(
            cap, _step("delete_step", tcid, "p1", "denied", result="Keep that step.")
        )
    calls = cap.tool_calls()
    assert [c.status for c in calls] == ["denied"] * LOOP_THRESHOLD
    assert calls[0].result == "Keep that step."
    assert calls[0].errors == []
    summary = cap.summary()
    assert summary.tool_calls == LOOP_THRESHOLD
    assert summary.failures == 0
    assert summary.loop_detected is False


def test_tokens_read_total_tokens_from_turn_usage(tmp_path: Path) -> None:
    cap = _new(tmp_path)
    _write(
        cap,
        {"type": "data-turn-usage", "data": {"totalTokens": 540898, "costUsd": "0.19"}},
    )
    s = cap.summary()
    assert s.tokens == 540898
    assert abs(s.cost_usd - 0.19) < 1e-9


def test_approval_tool_name_comes_from_tool_input(tmp_path: Path) -> None:
    cap = _new(tmp_path)
    _write(
        cap,
        {"type": "tool-input-available", "toolCallId": "ca", "toolName": "submit_plan"},
    )
    _write(
        cap, {"type": "tool-approval-request", "approvalId": "ca", "toolCallId": "ca"}
    )
    assert cap.pending_approval == ("submit_plan", "ca")


def test_flush_writes_full_fidelity_artifacts(tmp_path: Path) -> None:
    cap = _new(tmp_path)
    big_args: JSONObject = {
        "steps": [{"parameters": {"text_expression": "odorant binding protein"}}]
    }
    _write(cap, _call("planning", "build_plan", "p1", "started"))
    _write(cap, _step("create_plan", "c1", "p1", "started", args=big_args))
    _write(cap, _step("create_plan", "c1", "p1", "completed", result="x" * 5000))
    out = cap.flush()
    assert (out / "events.jsonl").exists()
    assert (out / "summary.json").exists()
    tool_files = sorted((out / "tools").glob("*.json"))
    assert len(tool_files) == 1
    payload = json.loads(tool_files[0].read_text())
    assert payload["args"] == big_args
    assert len(payload["result"]) == 5000  # not truncated on disk


def test_reset_run_dir_removes_stale_artifacts_keeps_unrelated(tmp_path: Path) -> None:
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "99-stale.json").write_text("{}")
    (tmp_path / "wdk").mkdir()
    (tmp_path / "wdk" / "01-old.json").write_text("{}")
    (tmp_path / "events.jsonl").write_text("old\n")
    (tmp_path / "diagnosis.json").write_text("[]")
    (tmp_path / "notes.txt").write_text("keep me")
    reset_run_dir(tmp_path)
    assert not (tmp_path / "tools" / "99-stale.json").exists()
    assert not (tmp_path / "wdk").exists()
    assert not (tmp_path / "events.jsonl").exists()
    assert not (tmp_path / "diagnosis.json").exists()
    assert (tmp_path / "notes.txt").read_text() == "keep me"
    assert tmp_path.is_dir()


def test_reset_run_dir_creates_missing_dir(tmp_path: Path) -> None:
    target = tmp_path / "fresh"
    reset_run_dir(target)
    assert target.is_dir()


def test_flush_after_reset_has_no_stale_tool_files(tmp_path: Path) -> None:
    stale = _new(tmp_path)
    _write(stale, _step("create_plan", "old1", "p1", "started"))
    _write(stale, _step("create_plan", "old1", "p1", "failed", result="boom"))
    stale.flush()
    assert (tmp_path / "tools" / "01-create_plan.json").exists()

    reset_run_dir(tmp_path)
    fresh = _new(tmp_path)
    _write(fresh, _step("think", "new1", "p1", "started"))
    _write(fresh, _step("think", "new1", "p1", "completed", result="ok"))
    fresh.flush()
    tool_files = sorted((tmp_path / "tools").glob("*.json"))
    assert [p.name for p in tool_files] == ["01-think.json"]


def test_events_jsonl_has_one_line_per_chunk(tmp_path: Path) -> None:
    cap = _new(tmp_path)
    _write(cap, {"type": "start", "messageId": "m"})
    _write(cap, {"type": "finish"})
    out = cap.flush()
    lines = (out / "events.jsonl").read_text().splitlines()
    assert len(lines) == 2


def test_capture_tracebacks_writes_exc_info(tmp_path: Path) -> None:
    logger = logging.getLogger("pathfinder.test.capture")
    msg = "synthetic boom"

    def _boom() -> None:
        raise ValueError(msg)

    with capture_tracebacks(tmp_path):
        try:
            _boom()
        except ValueError:
            logger.exception("tool blew up")
    files = sorted((tmp_path / "errors").glob("*.txt"))
    assert len(files) == 1
    body = files[0].read_text()
    assert "ValueError: synthetic boom" in body
    assert "Traceback" in body


def test_capture_tracebacks_ignores_non_exception_logs(tmp_path: Path) -> None:
    logger = logging.getLogger("pathfinder.test.capture2")
    with capture_tracebacks(tmp_path):
        logger.info("just info, no exception")
    assert not (tmp_path / "errors").exists() or not list(
        (tmp_path / "errors").glob("*.txt")
    )


def test_capture_tracebacks_captures_structlog_field_traceback(tmp_path: Path) -> None:
    logger = logging.getLogger("pathfinder.test.capture3")
    with capture_tracebacks(tmp_path):
        logger.error(
            "Unknown tool error", extra={"traceback": "Traceback: AppNotOpen boom"}
        )
    files = sorted((tmp_path / "errors").glob("*.txt"))
    assert len(files) == 1
    assert "AppNotOpen boom" in files[0].read_text()


def _ledger(phase: str, zero_steps: list[str]) -> JSONObject:
    build: JSONObject = {"zeroResultSteps": list(zero_steps)}
    return {
        "type": "data-ledger-update",
        "data": {"phase": phase, "build": build},
    }


def _text(delta: str) -> JSONObject:
    return {"type": "text-delta", "delta": delta}


class TestReplyCapture:
    def test_deltas_reassemble_into_the_reply(self, tmp_path: Path) -> None:
        cap = RunCapture(
            conversation_id=uuid4(), turn_id=uuid4(), run_dir=tmp_path, quiet=True
        )
        for part in ("That step ", "returned 0 genes."):
            _write(cap, _text(part))

        assert cap.assistant_text() == "That step returned 0 genes."

    def test_the_transcript_records_the_reply(self, tmp_path: Path) -> None:
        # The transcript listed only tool calls, so the one thing the
        # researcher actually read was missing from the run directory.
        cap = RunCapture(
            conversation_id=uuid4(), turn_id=uuid4(), run_dir=tmp_path, quiet=True
        )
        _write(cap, _text("No overlap between those sets."))
        cap.flush()

        assert (
            "No overlap between those sets." in (tmp_path / "transcript.md").read_text()
        )

    def test_a_run_with_no_text_has_an_empty_reply(self, tmp_path: Path) -> None:
        cap = RunCapture(
            conversation_id=uuid4(), turn_id=uuid4(), run_dir=tmp_path, quiet=True
        )
        assert cap.assistant_text() == ""


class TestDiagnosisReadsTheReply:
    def test_zero_results_explained_in_the_reply_is_not_an_anomaly(
        self, tmp_path: Path
    ) -> None:
        cap = RunCapture(
            conversation_id=uuid4(), turn_id=uuid4(), run_dir=tmp_path, quiet=True
        )
        _write(cap, _ledger("execution", ["s1"]))
        _write(cap, _text("The intersection returned 0 genes, so there is no overlap."))

        assert not [a for a in cap.anomalies() if a.kind == "silent_zero"]

    def test_zero_results_left_unsaid_is_still_an_anomaly(self, tmp_path: Path) -> None:
        cap = RunCapture(
            conversation_id=uuid4(), turn_id=uuid4(), run_dir=tmp_path, quiet=True
        )
        _write(cap, _ledger("execution", ["s1"]))
        _write(cap, _text("Your strategy is ready."))

        assert [a for a in cap.anomalies() if a.kind == "silent_zero"]


def _fixture_run() -> list[JSONObject]:
    path = Path(__file__).parent / "site_help_mock_run.events.jsonl"
    event: TypeAdapter[JSONObject] = TypeAdapter(JSONObject)
    return [event.validate_json(line) for line in path.read_text().splitlines() if line]


def test_a_one_agent_run_counts_the_calls_its_event_log_announces(
    tmp_path: Path,
) -> None:
    """A recorded site_help turn holds one ``tool-input-available``."""
    cap = _new(tmp_path)
    for chunk in _fixture_run():
        _write(cap, chunk)

    assert cap.summary().tool_calls == 1


def test_a_call_announced_twice_counts_once(tmp_path: Path) -> None:
    cap = _new(tmp_path)
    announce: JSONObject = {
        "type": "tool-input-available",
        "toolCallId": "call-1",
        "toolName": "list_veupathdb_sites",
        "input": {},
    }
    _write(cap, announce)
    _write(cap, announce)

    assert cap.summary().tool_calls == 1
    assert [call.tool for call in cap.tool_calls()] == ["list_veupathdb_sites"]


def test_a_lead_run_counts_its_dispatches_and_its_inner_steps(
    tmp_path: Path,
) -> None:
    cap = _new(tmp_path)
    _write(cap, _call("frame", "framer", "p1", "started"))
    _write(
        cap,
        {
            "type": "tool-input-available",
            "toolCallId": "p1",
            "toolName": "dispatch_frame",
            "input": {},
        },
    )
    _write(cap, _step("search_catalog", "c1", "p1", "started"))
    _write(cap, _step("search_catalog", "c1", "p1", "completed", result="2 hits"))

    assert cap.summary().tool_calls == 2


def test_the_transcript_names_a_durable_call_the_run_declined(tmp_path: Path) -> None:
    """A run with no worker must be readable afterwards: the refusal is in the file."""
    refusal = durable_call_refusal("run_control_tests_on_step")
    cap = _new(tmp_path)
    _write(cap, _call("verification", "verification", "p1", "started"))
    _write(cap, _step("run_control_tests_on_step", "c1", "p1", "started", args={}))
    _write(
        cap, _step("run_control_tests_on_step", "c1", "p1", "completed", result=refusal)
    )

    cap.flush()

    transcript = (tmp_path / "transcript.md").read_text()
    assert refusal in transcript
    assert json.loads((tmp_path / "summary.json").read_text())["tool_calls"] == 1


def _lead_input(tool: str, tcid: str, args: JSONObject) -> JSONObject:
    return {
        "type": "tool-input-available",
        "toolCallId": tcid,
        "toolName": tool,
        "input": args,
    }


def _lead_output(tcid: str, output: str) -> JSONObject:
    return {"type": "tool-output-available", "toolCallId": tcid, "output": output}


def _lead_error(tcid: str, error: str) -> JSONObject:
    return {"type": "tool-output-error", "toolCallId": tcid, "errorText": error}


def test_the_transcript_names_the_calls_the_lead_made_itself(tmp_path: Path) -> None:
    """A turn that dispatches nothing still has its own calls to read."""
    refusal = durable_call_refusal("optimize_search_parameters")
    cap = _new(tmp_path)
    _write(cap, _lead_input("optimize_search_parameters", "c1", {"wdk_step_id": 132}))
    _write(cap, _lead_output("c1", refusal))

    cap.flush()

    transcript = (tmp_path / "transcript.md").read_text()
    assert "- [lead] optimize_search_parameters" in transcript
    assert refusal in transcript
    assert (tmp_path / "tools" / "01-optimize_search_parameters.json").exists()


def test_a_lead_call_that_failed_reads_as_failed(tmp_path: Path) -> None:
    cap = _new(tmp_path)
    _write(cap, _lead_input("export_gene_set", "c1", {"gene_set_id": "gs_1"}))
    _write(cap, _lead_error("c1", "NOT_FOUND: no such gene set"))

    cap.flush()

    calls = cap.tool_calls()
    assert [(c.tool, c.status, c.result) for c in calls] == [
        ("export_gene_set", "failed", "NOT_FOUND: no such gene set")
    ]
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["failures"] == 1
    assert summary["status"] == "ok"


def test_a_parked_call_stays_open_in_the_transcript(tmp_path: Path) -> None:
    """A durable call the worker answers later has no output in this turn."""
    cap = _new(tmp_path)
    _write(cap, _lead_input("run_eda_compute", "c1", {}))

    cap.flush()

    transcript = (tmp_path / "transcript.md").read_text()
    assert "- [lead] run_eda_compute" in transcript
    assert "started" in transcript


_WDK_ERROR = "VEuPathDB service error: WDK_SERVICE_ERROR 500 on /users/current"


def test_a_lead_stuck_on_one_tool_reads_as_a_loop_in_both_artifacts(
    tmp_path: Path,
) -> None:
    """The summary and the diagnosis answer one run the same way."""
    cap = _new(tmp_path)
    for index in range(LOOP_THRESHOLD):
        tcid = f"c{index}"
        _write(cap, _lead_input("export_gene_set", tcid, {"gene_set_id": "gs_1"}))
        _write(cap, _lead_error(tcid, _WDK_ERROR))

    cap.flush()

    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["loop_detected"] is True
    assert summary["failures"] == LOOP_THRESHOLD
    kinds = [a["kind"] for a in json.loads((tmp_path / "diagnosis.json").read_text())]
    assert "loop" in kinds


def test_a_failed_lead_call_decodes_its_errors(tmp_path: Path) -> None:
    """The catch-22 detector reads `call.errors`, so a turn's own calls fill it."""
    cap = _new(tmp_path)
    _write(cap, _lead_input("create_plan", "c1", {"steps": []}))
    _write(
        cap,
        _lead_error(
            "c1",
            '{"ok": false, "code": "VALIDATION_ERROR", '
            '"message": "Missing required parameters: document_type", '
            '"details": {"errors": [{"context": {"searchName": "GenesByText", '
            '"missing": ["document_type"]}}]}}',
        ),
    )

    call = cap.tool_calls()[0]

    assert [(e.kind, e.param) for e in call.errors] == [
        ("missing_required", "document_type")
    ]


def test_a_tool_that_recovers_is_no_longer_looping(tmp_path: Path) -> None:
    """A success clears the count, as it does for a sub-agent's own call."""
    cap = _new(tmp_path)
    for index in range(LOOP_THRESHOLD - 1):
        tcid = f"c{index}"
        _write(cap, _lead_input("export_gene_set", tcid, {}))
        _write(cap, _lead_error(tcid, _WDK_ERROR))
    _write(cap, _lead_input("export_gene_set", "ok", {}))
    _write(cap, _lead_output("ok", "the file is ready"))
    _write(cap, _lead_input("export_gene_set", "again", {}))
    _write(cap, _lead_error("again", _WDK_ERROR))

    assert cap.summary().loop_detected is False


def test_a_terminal_call_that_answered_is_not_a_row_anywhere(tmp_path: Path) -> None:
    """The reply the output tool carries is the transcript's own section."""
    cap = _new(tmp_path)
    _write(cap, _lead_input("classify_user_intent", "c1", {}))
    _write(cap, _lead_output("c1", "new_strategy"))
    _write(cap, _lead_input(OUTPUT_TOOL, "c2", {"prose": "here is what I found"}))
    _write(cap, _lead_output("c2", "Final result processed."))

    cap.flush()

    assert [call.tool for call in cap.rendered_calls()] == ["classify_user_intent"]
    assert OUTPUT_TOOL not in (tmp_path / "transcript.md").read_text()
    assert OUTPUT_TOOL not in (tmp_path / "tree.txt").read_text()
    assert [path.name for path in sorted((tmp_path / "tools").iterdir())] == [
        "01-classify_user_intent.json"
    ]
    assert cap.summary().tool_calls == 2


def test_a_terminal_call_the_model_kept_failing_reads_as_a_loop(
    tmp_path: Path,
) -> None:
    """An output the model cannot produce is the loop the debugger must show."""
    cap = _new(tmp_path)
    for index in range(LOOP_THRESHOLD):
        tcid = f"c{index}"
        _write(cap, _lead_input(OUTPUT_TOOL, tcid, {"prose": ""}))
        _write(cap, _lead_error(tcid, "prose: Field required"))

    cap.flush()

    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["failures"] == LOOP_THRESHOLD
    assert summary["loop_detected"] is True
    kinds = [a["kind"] for a in json.loads((tmp_path / "diagnosis.json").read_text())]
    assert "loop" in kinds
    assert OUTPUT_TOOL in (tmp_path / "transcript.md").read_text()
