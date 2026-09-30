"""Calls that complete with arguments an earlier call already read are a loop, and
the summary and the diagnosis read loops by one rule."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from assistant_core.platform.types import JSONObject

from pathfinder.devtools.capture import RunCapture
from pathfinder.devtools.diagnosis import LOOP_THRESHOLD, loops
from pathfinder.devtools.models import CapturedToolCall

# Five LdBPK ids a Lead read again and again in one turn.
_IDS = (
    "LdBPK_010310.1",
    "LdBPK_030050.1",
    "LdBPK_040440.1",
    "LdBPK_041170.1",
    "LdBPK_050090.1",
)
_READ = "read_gene_record"


def _new(tmp_path: Path) -> RunCapture:
    return RunCapture(
        conversation_id=uuid4(), turn_id=uuid4(), run_dir=tmp_path, quiet=True
    )


def _write(capture: RunCapture, chunk: JSONObject) -> None:
    asyncio.run(capture.write(chunk))


def _read_cycle(capture: RunCapture, rounds: int) -> None:
    for index in range(rounds * len(_IDS)):
        tcid = f"c{index}"
        gene = _IDS[index % len(_IDS)]
        _write(
            capture,
            {
                "type": "tool-input-available",
                "toolCallId": tcid,
                "toolName": _READ,
                "input": {"gene_id": gene},
            },
        )
        _write(
            capture,
            {"type": "tool-output-available", "toolCallId": tcid, "output": gene},
        )


def _completed(seq: int, gene: str) -> CapturedToolCall:
    return CapturedToolCall(
        seq=seq,
        tool=_READ,
        tool_call_id=f"c{seq}",
        status="completed",
        args={"gene_id": gene},
        result=gene,
    )


def test_a_cycle_of_identical_reads_is_a_loop_in_both_artifacts(
    tmp_path: Path,
) -> None:
    capture = _new(tmp_path)
    _read_cycle(capture, rounds=9)

    capture.flush()

    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["loop_detected"] is True
    assert summary["failures"] == 0
    [loop] = [
        a
        for a in json.loads((tmp_path / "diagnosis.json").read_text())
        if a["kind"] == "loop"
    ]
    assert loop["details"]["tool"] == _READ
    assert loop["details"]["identical_completions"] == 40
    assert "40 calls" in loop["message"]


def test_reads_of_different_records_are_no_loop() -> None:
    calls = [_completed(seq, f"gene_{seq}") for seq in range(1, 20)]

    assert loops(calls) == []


def test_repeats_under_the_threshold_are_no_loop() -> None:
    first = [_completed(seq, gene) for seq, gene in enumerate(_IDS, start=1)]
    again = [
        _completed(seq, _IDS[0])
        for seq in range(len(first) + 1, len(first) + LOOP_THRESHOLD)
    ]

    assert loops(first + again) == []
