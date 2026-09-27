"""A control test runs against one saved control set, named by its id."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.platform.db import DBSessionFactory
from pydantic_ai.exceptions import CallDeferred, ModelRetry
from veupathdb_mcp.controls import (
    ControlTargetData,
    ControlTestResult,
    NegativeControls,
    PositiveControls,
)
from veupathdb_mcp.tool_payloads import ControlOutcome

from pathfinder.ai.tools.standalone import experiment
from pathfinder.ai.tools.standalone.control_repeats import merged_control_tests
from pathfinder.domain.evidence import (
    ControlSetEvidence,
    ControlTestEvidence,
    NamedControlSet,
)
from pathfinder.services.control_sets import ControlSetResponse
from pathfinder.services.evidence.control_sets import (
    SavedControls,
    UnknownControlSetError,
)
from pathfinder.services.experiment.published_names import PublishedNames
from pathfinder.tests._support.durable_dispatch import capture_durable_dispatch
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context, summary_of

_SAVED = SavedControls(
    control_set_id="5f1c6a2e-0000-4000-8000-00000000c0de",
    name="Signal peptide controls",
    positive_ids=["PF3D7_1031000", "PF3D7_1222600", "PF3D7_0000001"],
    negative_ids=["PF3D7_0102600"],
)
_OTHER_ID = "0b7e2c11-0000-4000-8000-0000000000aa"
_LISTED = ControlSetResponse(
    id=_SAVED.control_set_id,
    name=_SAVED.name,
    site_id="plasmodb",
    record_type="transcript",
    positive_ids=_SAVED.positive_ids,
    negative_ids=_SAVED.negative_ids,
    tags=[],
    version=1,
    is_public=False,
    created_at="2026-09-27T00:00:00+00:00",
)
_STEP = 440912333
_ATTACHED = [
    NamedControlSet(id=_SAVED.control_set_id, name=_SAVED.name),
    NamedControlSet(id=_OTHER_ID, name="A set since deleted"),
    NamedControlSet(id="g1", name="Not a set id"),
]


class _Reads:
    def __init__(self) -> None:
        self.asked: list[tuple[str, str, UUID | None]] = []


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> _Reads:
    """The one saved set of the site, read as the facade reads it."""
    seen = _Reads()

    async def saved(
        db_session_factory: DBSessionFactory | None,
        control_set_id: str,
        *,
        site_id: str,
        user_id: UUID | None,
    ) -> SavedControls:
        del db_session_factory
        seen.asked.append((control_set_id, site_id, user_id))
        if control_set_id != _SAVED.control_set_id:
            raise UnknownControlSetError(control_set_id, [_LISTED])
        return _SAVED

    monkeypatch.setattr(experiment, "saved_control_set", saved)
    return seen


@pytest.fixture
def measured(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """The ids each search test measured, answered as the site would."""
    asked: list[dict[str, Any]] = []

    async def run(config: Any, **controls: Any) -> ControlTestResult:
        del config
        asked.append(controls)
        return ControlTestResult(
            target=ControlTargetData(
                search_name="GenesWithSignalPeptide", step_id=901, estimated_size=479
            ),
            positive=PositiveControls(
                recovered_ids=_SAVED.positive_ids[:2],
                missed_ids=_SAVED.positive_ids[2:],
            ),
            negative=NegativeControls(
                admitted_ids=[], excluded_ids=_SAVED.negative_ids
            ),
        )

    async def no_export(outcome: ControlOutcome, name: str) -> ControlOutcome:
        del name
        return outcome

    async def published(site_id: str, record_type: str, search: str) -> PublishedNames:
        del site_id, record_type, search
        return PublishedNames(label="Predicted Signal Peptide")

    async def knobs(site_id: str, record_type: str, search: str) -> list[str]:
        del site_id, record_type, search
        return []

    monkeypatch.setattr(experiment, "run_positive_negative_controls", run)
    monkeypatch.setattr(experiment, "attach_control_downloads", no_export)
    monkeypatch.setattr(experiment, "published_names", published)
    monkeypatch.setattr(experiment, "tunable_parameters_of_search", knobs)
    return asked


async def test_the_step_test_defers_the_id_of_the_saved_set(
    reads: _Reads, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatch = capture_durable_dispatch(monkeypatch)
    ctx = agent_run_context(control_sets=_ATTACHED)
    ctx.deps.conversation_id = uuid4()

    with pytest.raises(CallDeferred):
        await experiment.run_control_tests_on_step(
            ctx, wdk_step_id=_STEP, control_set_id=_SAVED.control_set_id
        )

    assert [row["args"] for row in dispatch.created] == [
        {
            "args": [],
            "kwargs": {"wdk_step_id": _STEP, "control_set_id": _SAVED.control_set_id},
        }
    ]
    assert reads.asked == [(_SAVED.control_set_id, "plasmodb", ctx.deps.user_id)]


async def test_an_attached_id_of_no_saved_set_is_refused_before_a_task_starts(
    reads: _Reads, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatch = capture_durable_dispatch(monkeypatch)
    ctx = agent_run_context(control_sets=_ATTACHED)
    ctx.deps.conversation_id = uuid4()

    with pytest.raises(ModelRetry) as refused:
        await experiment.run_control_tests_on_step(
            ctx, wdk_step_id=_STEP, control_set_id=_OTHER_ID
        )

    assert dispatch.created == []
    assert str(refused.value) == (
        f"control_set_id '{_OTHER_ID}' names no control set saved on this site. "
        f"The saved control sets: {_SAVED.control_set_id} (Signal peptide "
        "controls). A control test runs only against a saved control set; "
        "list_control_sets names them. With none, state that no controls were "
        "available."
    )
    assert len(reads.asked) == 1


async def test_the_search_test_measures_the_ids_the_saved_set_holds(
    reads: _Reads, measured: list[dict[str, Any]]
) -> None:
    ctx = agent_run_context(tool_call_id="call_search_controls", control_sets=_ATTACHED)

    returned = await experiment.run_control_tests_on_search(
        ctx, "GenesWithSignalPeptide", {}, control_set_id=_SAVED.control_set_id
    )

    assert measured == [
        {
            "positive_controls": _SAVED.positive_ids,
            "negative_controls": _SAVED.negative_ids,
        }
    ]
    (run,) = ctx.deps.turn_markers.control_tests
    assert run.evidence.control_set == NamedControlSet(
        id=_SAVED.control_set_id, name="Signal peptide controls"
    )
    assert summary_of(returned).data["summary"] == (
        "2 of 3 positive controls recovered; recall 0.67, precision 1.00, "
        "MCC 0.58; no tunable parameters"
    )
    assert len(reads.asked) == 1


async def test_the_search_test_refuses_an_attached_id_of_no_saved_set(
    reads: _Reads, measured: list[dict[str, Any]]
) -> None:
    ctx = agent_run_context(control_sets=_ATTACHED)

    with pytest.raises(ModelRetry, match="names no control set saved on this site"):
        await experiment.run_control_tests_on_search(
            ctx, "GenesWithSignalPeptide", {}, control_set_id="g1"
        )

    assert measured == []
    assert reads.asked == [("g1", "plasmodb", ctx.deps.user_id)]


def test_the_worker_answer_names_the_set_it_ran() -> None:
    answer = ControlOutcome(
        step_id=_STEP,
        positive_recovered_ids=_SAVED.positive_ids,
        positive_missed_ids=[],
    ).model_dump(by_alias=True, exclude_none=True, mode="json")
    answer["controlSet"] = {"id": _SAVED.control_set_id, "name": _SAVED.name}

    run = experiment.control_test_run(answer, tool_call_id="call_controls")

    assert run is not None
    assert run.evidence.control_set == NamedControlSet(
        id=_SAVED.control_set_id, name="Signal peptide controls"
    )


def test_two_sets_tested_on_one_step_stay_two_tests_on_the_card() -> None:
    first = NamedControlSet(id=_SAVED.control_set_id, name=_SAVED.name)
    second = NamedControlSet(id=_OTHER_ID, name="Apicoplast controls")
    tests = [
        ControlTestEvidence(
            tested_label="Predicted Signal Peptide",
            wdk_step_id=_STEP,
            control_set=named,
            positive=ControlSetEvidence(returned=[gene], not_returned=[]),
        )
        for named, gene in ((first, "PF3D7_1031000"), (second, "PF3D7_0102200"))
    ]

    merged = merged_control_tests(tests)

    assert [(t.control_set, t.positive) for t in merged] == [
        (first, ControlSetEvidence(returned=["PF3D7_1031000"], not_returned=[])),
        (second, ControlSetEvidence(returned=["PF3D7_0102200"], not_returned=[])),
    ]
