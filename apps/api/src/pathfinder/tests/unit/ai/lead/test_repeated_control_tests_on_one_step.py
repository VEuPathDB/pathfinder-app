"""One message tests one step's controls once, and its card holds every id tested.

The fixture is the call sequence a VERIFY pass made on the signal peptide step:
the whole 80 and 40 control set first, then 51 calls on subsets of it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.tasks import decorator, service
from pydantic import Field
from pydantic_ai.exceptions import CallDeferred
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.graph.turn_records import ControlTestRun
from pathfinder.ai.lead.evidence_card import CardSources, assemble_evidence_card
from pathfinder.ai.tools.standalone.control_repeats import RepeatedControlTest
from pathfinder.ai.tools.standalone.experiment import (
    control_test_run,
    run_control_tests_on_step,
)
from pathfinder.domain.evidence import EvidenceVerdict, VerificationReview
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.lead.conftest import ChunkCollector
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context, summary_of

_FIXTURE = (
    Path(__file__).parents[3]
    / "fixtures"
    / "controls"
    / "signal_peptide_repeated_tests.json"
)


class _Call(CamelModel):
    positive: list[str] | None = None
    negative: list[str] | None = None


class _Sequence(CamelModel):
    wdk_step_id: int
    tested_label: str
    returned: list[str]
    calls: list[_Call] = Field(default_factory=list)


_SEQUENCE = _Sequence.model_validate(json.loads(_FIXTURE.read_text()))


def _worker_result(call: _Call) -> dict[str, Any]:
    """What the worker reports for one call, read from the step's gene ids."""
    returned = set(_SEQUENCE.returned)
    result: dict[str, Any] = {
        "stepId": _SEQUENCE.wdk_step_id,
        "targetLabel": _SEQUENCE.tested_label,
    }
    if call.positive is not None:
        result["positiveRecoveredIds"] = [i for i in call.positive if i in returned]
        result["positiveMissedIds"] = [i for i in call.positive if i not in returned]
    if call.negative is not None:
        result["negativeAdmittedIds"] = [i for i in call.negative if i in returned]
        result["negativeExcludedIds"] = [i for i in call.negative if i not in returned]
    return result


def _every_call_run() -> list[ControlTestRun]:
    runs = [
        control_test_run(_worker_result(call), tool_call_id=f"call_{index}")
        for index, call in enumerate(_SEQUENCE.calls)
    ]
    return [run for run in runs if run is not None]


def _card(runs: list[ControlTestRun]) -> list[tuple[str, int, int, int, float]]:
    sources = CardSources(
        check_id="call_verify",
        revision="rev-1",
        site_id="plasmodb",
        labels={},
        live_wdk_step_ids=frozenset({_SEQUENCE.wdk_step_id}),
        wdk_strategy_id=None,
        root_wdk_step_id=None,
        node_results=(),
        spec=None,
        control_tests=tuple(runs),
        verdict=EvidenceVerdict(supported=True),
        review=VerificationReview(),
    )
    card = assemble_evidence_card(
        sources, None, checked_at=datetime(2026, 9, 24, tzinfo=UTC)
    )
    rows: list[tuple[str, int, int, int, float]] = []
    for tested in card.controls:
        for kind, held in (
            ("Positive", tested.positive),
            ("Negative", tested.negative),
        ):
            if held is not None:
                rows.append(
                    (
                        kind,
                        held.controls_count,
                        held.returned_count,
                        len(held.not_returned),
                        round(held.rate, 2),
                    )
                )
    return rows


def test_the_card_of_the_whole_sequence_holds_every_id_once() -> None:
    assert len(_SEQUENCE.calls) == 52

    assert _card(_every_call_run()) == [
        ("Positive", 80, 52, 28, 0.65),
        ("Negative", 40, 2, 38, 0.05),
    ]


class _Tasks:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def configure_task(self, **kwargs: Any) -> _Tasks:
        del kwargs
        return self

    async def defer_async(self, **kwargs: Any) -> None:
        del kwargs


@pytest.fixture
def tasks(monkeypatch: pytest.MonkeyPatch) -> _Tasks:
    recorder = _Tasks()

    async def _create(**kwargs: Any) -> UUID:
        recorder.created.append(kwargs)
        return uuid4()

    monkeypatch.setattr(decorator, "create_background_task", _create)
    monkeypatch.setattr(service, "task_app", lambda: recorder)
    monkeypatch.setattr(decorator, "get_stream_writer", ChunkCollector)
    return recorder


async def test_the_sequence_starts_one_task_and_answers_the_rest(
    tasks: _Tasks,
) -> None:
    ctx = agent_run_context()
    ctx.deps.conversation_id = uuid4()
    markers = ctx.deps.turn_markers
    answered: list[ToolReturn[Any]] = []

    for index, call in enumerate(_SEQUENCE.calls):
        ctx.tool_call_id = f"call_{index}"
        try:
            answered.append(
                await run_control_tests_on_step(
                    ctx,
                    wdk_step_id=_SEQUENCE.wdk_step_id,
                    positive_controls=call.positive,
                    negative_controls=call.negative,
                )
            )
        except CallDeferred:
            run = control_test_run(_worker_result(call), tool_call_id=f"call_{index}")
            assert run is not None
            markers.record_control_tests([run])

    assert len(tasks.created) == 1
    assert len(answered) == 51
    assert _card(markers.control_tests) == [
        ("Positive", 80, 52, 28, 0.65),
        ("Negative", 40, 2, 38, 0.05),
    ]


async def test_a_repeat_answers_the_ids_it_asked_about(tasks: _Tasks) -> None:
    ctx = agent_run_context()
    ctx.deps.conversation_id = uuid4()
    first = _SEQUENCE.calls[0]
    run = control_test_run(_worker_result(first), tool_call_id="call_0")
    assert run is not None
    ctx.deps.turn_markers.record_control_tests([run])
    negatives = ["PF3D7_1111100", "PF3D7_1215900", "PF3D7_1429900"]

    ctx.tool_call_id = "call_1"
    answer = await run_control_tests_on_step(
        ctx, wdk_step_id=_SEQUENCE.wdk_step_id, negative_controls=negatives
    )

    assert tasks.created == []
    body = returned(answer, RepeatedControlTest).model_dump(by_alias=True, mode="json")
    assert body["outcome"]["negativeAdmittedIds"] == ["PF3D7_1215900"]
    assert body["outcome"]["negativeExcludedIds"] == [
        "PF3D7_1111100",
        "PF3D7_1429900",
    ]
    assert body["outcome"]["positiveRecoveredIds"] is None
    assert summary_of(answer).model_dump(by_alias=True)["data"]["summary"] == (
        "Already tested on this step: 3 negative controls: 1 returned"
    )


async def test_an_id_not_yet_tested_starts_a_task(tasks: _Tasks) -> None:
    ctx = agent_run_context()
    ctx.deps.conversation_id = uuid4()
    run = control_test_run(_worker_result(_SEQUENCE.calls[0]), tool_call_id="call_0")
    assert run is not None
    ctx.deps.turn_markers.record_control_tests([run])

    ctx.tool_call_id = "call_1"
    with pytest.raises(CallDeferred):
        await run_control_tests_on_step(
            ctx,
            wdk_step_id=_SEQUENCE.wdk_step_id,
            positive_controls=["PF3D7_0100600", "PF3D7_1133400"],
        )

    assert len(tasks.created) == 1
