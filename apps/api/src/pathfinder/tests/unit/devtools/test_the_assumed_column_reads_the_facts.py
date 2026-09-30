"""The ``assumed`` column counts the narrowing values the request did not state
that the last facts part does not show with who set them."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from veupathdb.domain.parameters import NumberValue

from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.devtools.capture import RunCapture, unshown_assumed_values
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    Measurement,
    OperationalSpec,
)
from pathfinder.domain.turn_facts import ParameterFact, StepFact, TurnFacts
from pathfinder.tests._support.bound_values import bound

_PERCENTILE = "min_expression_percentile"
_NAME = "Minimum expression percentile"


def _checkpointed() -> dict[str, object]:
    spec = OperationalSpec(
        goal="trophozoite genes",
        criteria=[
            Criterion(
                id="c_rna",
                text="expressed in trophozoites",
                search_name="GenesByRNASeqPercentile",
                resolved_params=bound(
                    {_PERCENTILE: NumberValue(value=80)}, defaulted=[_PERCENTILE]
                ),
                param_display_names={_PERCENTILE: _NAME},
                measurements=[
                    Measurement(
                        kind="loosest_bound", param=_PERCENTILE, count=8201, reading="0"
                    )
                ],
                result_count=1665,
            )
        ],
    )
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="amoebadb",
        mode="strategy",
        domain=StrategyDomainState(operational_spec=spec),
    )
    return state.model_dump()


def _facts(notes: list[str]) -> TurnFacts:
    row = ParameterFact(
        name=_PERCENTILE, display_name=_NAME, value="80", source="default", notes=notes
    )
    return TurnFacts(
        steps=[StepFact(step_id="c_rna", display_name="RNA-Seq", parameters=[row])]
    )


def test_a_default_the_facts_show_with_its_measurement_counts_nothing() -> None:
    assert unshown_assumed_values(_checkpointed(), _facts(["at 0: 8,201"])) == 0


def test_a_default_the_facts_do_not_carry_counts_once() -> None:
    assert unshown_assumed_values(_checkpointed(), _facts([])) == 1
    assert unshown_assumed_values(_checkpointed(), None) == 1


def test_the_run_summary_carries_the_assumed_count(tmp_path: Path) -> None:
    """summary.json counts the defaults the last facts part does not carry."""
    capture = RunCapture(
        conversation_id=uuid4(), turn_id=uuid4(), run_dir=tmp_path, quiet=True
    )
    facts = _facts([]).model_dump(by_alias=True, mode="json")
    asyncio.run(capture.write({"type": "data-facts", "data": facts}))
    capture.note_checkpoint(_checkpointed())

    out = capture.flush()

    assert json.loads((out / "summary.json").read_text())["assumed"] == 1
    assert capture.summary().assumed == 1


def test_a_run_whose_checkpoint_was_not_read_counts_no_assumed(tmp_path: Path) -> None:
    capture = RunCapture(
        conversation_id=uuid4(), turn_id=uuid4(), run_dir=tmp_path, quiet=True
    )

    out = capture.flush()

    assert capture.summary().assumed is None
    assert json.loads((out / "summary.json").read_text())["assumed"] is None
    assert json.loads((out / "summary.json").read_text())["tool_calls"] == 0
