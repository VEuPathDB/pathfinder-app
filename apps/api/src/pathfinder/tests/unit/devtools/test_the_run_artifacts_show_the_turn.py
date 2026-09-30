"""The transcript shows the facts part before the reply, and each tool file holds
the whole value the tool returned to the model."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from assistant_core.platform.types import JSONObject

from pathfinder.devtools.capture import (
    WORKER_RUN_ROOT,
    RunCapture,
    collect_worker_llm,
    worker_llm_dir,
)
from pathfinder.domain.turn_facts import ParameterFact, StepFact, TurnFacts

# A study step checked against a 1.5-fold request, as the check returns it.
_CHECKED: JSONObject = {
    "stepId": "step_eda",
    "recordCount": 1249,
    "checks": [
        {
            "label": "fold-change cutoff",
            "requested": "1.5",
            "realized": "2.82843",
            "honored": False,
        }
    ],
}


def _new(tmp_path: Path) -> RunCapture:
    return RunCapture(
        conversation_id=uuid4(), turn_id=uuid4(), run_dir=tmp_path, quiet=True
    )


def _write(capture: RunCapture, chunk: JSONObject) -> None:
    asyncio.run(capture.write(chunk))


def _step(state: str, result: str | None = None) -> JSONObject:
    return {
        "type": "data-sub-agent-step",
        "data": {
            "toolName": "check_study_step",
            "toolCallId": "call_check",
            "parentToolCallId": "call_verify",
            "state": state,
            "args": {"step_id": "step_eda", "requested_fold_change": 1.5},
            "resultSummary": result,
        },
    }


def _model_request(tmp_path: Path) -> None:
    llm = tmp_path / "llm"
    llm.mkdir(parents=True)
    request = {
        "role": "verification",
        "messages": [
            {
                "kind": "request",
                "parts": [
                    {
                        "part_kind": "tool-return",
                        "tool_name": "check_study_step",
                        "tool_call_id": "call_check",
                        "content": _CHECKED,
                    }
                ],
            }
        ],
    }
    (llm / "0001-verification-request.json").write_text(json.dumps(request))


def test_the_transcript_shows_the_facts_before_the_reply(tmp_path: Path) -> None:
    capture = _new(tmp_path)
    facts = TurnFacts(
        steps=[
            StepFact(
                step_id="c_tm",
                display_name="Transmembrane Domain Count",
                count=1183,
                parameters=[
                    ParameterFact(
                        name="min_tm",
                        display_name="Minimum TM domains",
                        value="1",
                        source="stated",
                    )
                ],
            )
        ],
        root_count=1183,
    )
    _write(
        capture,
        {"type": "data-facts", "data": facts.model_dump(by_alias=True, mode="json")},
    )
    _write(capture, {"type": "text-delta", "delta": "The step is shown beside this."})

    transcript = (capture.flush() / "transcript.md").read_text()

    shown = transcript.split("## Facts\n\n", 1)[1].split("\n\n## Assumed", 1)[0]
    assert shown.splitlines() == [
        "Strategy",
        "Transmembrane Domain Count: 1,183 genes",
        "  Minimum TM domains: 1 (stated)",
        "Result: 1,183 genes",
        "",
        "## Reply",
        "",
        "The step is shown beside this.",
    ]


def test_a_tool_file_holds_the_whole_value_the_model_read(tmp_path: Path) -> None:
    capture = _new(tmp_path)
    _model_request(tmp_path)
    _write(capture, _step("started"))
    _write(capture, _step("completed", "1,249 records at 2.82843-fold"))

    out = capture.flush()

    written = json.loads((out / "tools" / "01-check_study_step.json").read_text())
    assert written["result"] == "1,249 records at 2.82843-fold"
    assert written["output"] == _CHECKED
    assert written["output"]["checks"][0]["honored"] is False


def test_a_tool_file_with_no_model_request_holds_no_output(tmp_path: Path) -> None:
    capture = _new(tmp_path)
    _write(capture, _step("started"))
    _write(capture, _step("completed", "1,249 records"))

    written = json.loads(
        (capture.flush() / "tools" / "01-check_study_step.json").read_text()
    )

    assert written["result"] == "1,249 records"
    assert written["output"] is None


def test_a_lead_call_holds_the_output_its_event_carried(tmp_path: Path) -> None:
    capture = _new(tmp_path)
    _write(
        capture,
        {
            "type": "tool-input-available",
            "toolCallId": "call_lead",
            "toolName": "check_study_step",
            "input": {"step_id": "step_eda"},
        },
    )
    _write(
        capture,
        {
            "type": "tool-output-available",
            "toolCallId": "call_lead",
            "output": _CHECKED,
        },
    )

    written = json.loads(
        (capture.flush() / "tools" / "01-check_study_step.json").read_text()
    )

    assert written["output"] == _CHECKED


def test_the_worker_writes_its_model_requests_under_the_shared_mount() -> None:
    turn = uuid4()

    assert worker_llm_dir(turn).is_relative_to(WORKER_RUN_ROOT)
    assert worker_llm_dir(turn).name == str(turn)


def test_a_worker_turn_s_model_requests_reach_a_run_dir_outside_the_mount(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "pf-runs"
    run_dir = tmp_path / "scratch" / "turn1"
    capture = RunCapture(
        conversation_id=uuid4(), turn_id=uuid4(), run_dir=run_dir, quiet=True
    )
    staged = shared / worker_llm_dir(capture.turn_id).relative_to(WORKER_RUN_ROOT)
    _model_request(staged)
    _write(capture, _step("started"))
    _write(capture, _step("completed", "1,249 records at 2.82843-fold"))

    moved = collect_worker_llm(shared, capture.turn_id, run_dir)

    assert moved is True
    assert not staged.exists()
    written = json.loads(
        (capture.flush() / "tools" / "01-check_study_step.json").read_text()
    )
    assert written["output"] == _CHECKED


def test_a_worker_turn_that_wrote_nothing_says_so(tmp_path: Path) -> None:
    assert collect_worker_llm(tmp_path, uuid4(), tmp_path / "run") is False
