"""The transcript shows every field the facts part holds, who set each value
included, and names the checkpoint's assumed count apart from the constraint
rows the Lead assumed."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

from assistant_core.platform.types import JSONObject

from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.devtools.capture import RunCapture
from pathfinder.domain.turn_facts import (
    ParameterFact,
    SourceFact,
    StepFact,
    TurnFacts,
)

_PERCENTILE = "min_expression_percentile"
_UNSHOWN = (
    "summary.assumed (narrowing values no message states that the facts part "
    "does not show): "
)
_LEDGER_ROWS = (
    "ledger constraint rows the Lead marked source=assumed "
    "(not counted in summary.assumed): "
)


def _new(tmp_path: Path) -> RunCapture:
    return RunCapture(
        conversation_id=uuid4(), turn_id=uuid4(), run_dir=tmp_path, quiet=True
    )


def _write(capture: RunCapture, chunk: JSONObject) -> None:
    asyncio.run(capture.write(chunk))


def _eda_facts() -> TurnFacts:
    return TurnFacts(
        draft=True,
        steps=[
            StepFact(
                step_id="c_eda",
                display_name="Differential expression",
                operator="INTERSECT",
                count=430,
                reason="Compare hyphae against yeast.",
                parameters=[
                    ParameterFact(
                        name="foldChange",
                        display_name="Fold change",
                        value="2",
                        source="chosen",
                        notes=["at 1.5: 612 genes"],
                    ),
                    ParameterFact(
                        name="direction",
                        display_name="Direction",
                        value="upOnly",
                        label="Up-regulated",
                        source="card",
                    ),
                    ParameterFact(
                        name="pValue",
                        display_name="Adjusted p-value",
                        value="0.05",
                        source="default",
                    ),
                ],
                error="The site refused the cutoff.",
            )
        ],
        root_count=430,
    )


def _empty_checkpoint() -> dict[str, object]:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        domain=StrategyDomainState(),
    )
    return state.model_dump()


def _facts_section(transcript: str) -> str:
    return transcript.split("## Facts\n\n", 1)[1].split("\n\n## ", 1)[0]


def test_each_parameter_row_shows_who_set_its_value(tmp_path: Path) -> None:
    capture = _new(tmp_path)
    facts = _eda_facts()
    _write(
        capture,
        {"type": "data-facts", "data": facts.model_dump(by_alias=True, mode="json")},
    )

    transcript = (capture.flush() / "transcript.md").read_text()

    assert _facts_section(transcript).splitlines() == [
        "Plan",
        "INTERSECT Differential expression: 430 genes",
        "  Compare hyphae against yeast.",
        "  Fold change: 2 (chosen)",
        "    at 1.5: 612 genes",
        "  Direction: upOnly (Up-regulated) (your answer)",
        "  Adjusted p-value: 0.05 (site default)",
        "  The site refused the cutoff.",
        "Result: 430 genes",
    ]


_EBI = "https://qa.hostdb.org/hostdb.qa/app/record/gene/EBI_26400"


def test_a_record_read_from_a_step_shows_under_that_step(tmp_path: Path) -> None:
    capture = _new(tmp_path)
    facts = TurnFacts(
        steps=[StepFact(step_id="step_af8c56ad", display_name="Text", count=9)],
        sources=[
            SourceFact(
                url=_EBI,
                record_id="EBI_26400",
                step_id="step_af8c56ad",
                step_name="Text",
                fit="yes",
            ),
            SourceFact(url=_EBI, record_id="EBI_26400", step_id="step_gone"),
        ],
        root_count=9,
    )
    _write(
        capture,
        {"type": "data-facts", "data": facts.model_dump(by_alias=True, mode="json")},
    )

    transcript = (capture.flush() / "transcript.md").read_text()

    assert _facts_section(transcript).splitlines() == [
        "Strategy",
        "Text: 9 genes",
        f"  Read from Text: EBI_26400 (the check judged its fit yes): {_EBI}",
        "Result: 9 genes",
        f"not shown, its step is not in the facts: Read: EBI_26400: {_EBI}",
    ]


def _ledger(source: str) -> JSONObject:
    return {
        "constraints": {
            "blocking": False,
            "unmetCount": 0,
            "grounded": [
                {
                    "constraint": {
                        "kind": "percentile",
                        "requestedValue": "95",
                        "label": _PERCENTILE,
                        "source": source,
                    },
                    "status": "grounded",
                },
                {
                    "constraint": {
                        "kind": "organism",
                        "requestedValue": "Plasmodium falciparum 3D7",
                        "label": "organism",
                        "source": "user_explicit",
                    },
                    "status": "grounded",
                },
            ],
        }
    }


def test_the_assumed_count_and_the_assumed_constraints_are_named_apart(
    tmp_path: Path,
) -> None:
    capture = _new(tmp_path)
    _write(capture, {"type": "data-ledger-update", "data": _ledger("assumed")})
    capture.note_checkpoint(_empty_checkpoint())

    transcript = (capture.flush() / "transcript.md").read_text()

    assert transcript.split("## Assumed\n\n", 1)[1].splitlines() == [
        _UNSHOWN + "0",
        _LEDGER_ROWS + "1",
        f"- {_PERCENTILE} (percentile): '95' -> grounded",
    ]


def test_a_run_that_read_no_checkpoint_says_it_counted_nothing(
    tmp_path: Path,
) -> None:
    capture = _new(tmp_path)
    _write(capture, {"type": "data-ledger-update", "data": _ledger("user_explicit")})

    transcript = (capture.flush() / "transcript.md").read_text()

    assert transcript.split("## Assumed\n\n", 1)[1].splitlines() == [
        _UNSHOWN + "not counted (no checkpoint read)",
        _LEDGER_ROWS + "0",
    ]
