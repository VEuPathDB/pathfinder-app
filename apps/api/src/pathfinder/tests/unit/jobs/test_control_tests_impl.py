"""The control-test worker reports WDK's own names for what it tested."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.platform.db import AsyncSession
from assistant_core.tasks.progress import TaskProgressEmitter
from veupathdb.domain.strategy.session import StrategySession
from veupathdb.errors import VEuPathDBError, VEuPathDBErrorCode
from veupathdb.wdk.wdk_models import WDKSearchConfig, WDKStep
from veupathdb_mcp.tool_payloads import ControlOutcome

from pathfinder.ai.graph.runtime import Context
from pathfinder.jobs.impls import control_tests_impl
from pathfinder.jobs.impls.control_tests_impl import run_control_tests_on_step_impl
from pathfinder.services.experiment.published_names import PublishedNames

STEP_ID = 440299573
SEARCH = "GenesByMolecularWeight"
LABEL = "Genes by Molecular Weight"


def _no_session() -> AsyncSession:
    msg = "this test writes nothing to the database"
    raise AssertionError(msg)


def _context() -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=_no_session,
        cancel_event=asyncio.Event(),
    )


def _emitter() -> TaskProgressEmitter:
    return TaskProgressEmitter(
        task_id=uuid4(),
        conversation_id=uuid4(),
        session_factory=_no_session,
    )


def _refused() -> VEuPathDBError:
    return VEuPathDBError(VEuPathDBErrorCode.WDK_ERROR, "no such step")


class _Api:
    """A strategy API that answers one step lookup."""

    def __init__(
        self, error: Exception | None = None, *, unnamed: bool = False
    ) -> None:
        self.error = error
        self.unnamed = unnamed

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        if self.error is not None:
            raise self.error
        return WDKStep(
            id=step_id,
            search_name=SEARCH,
            display_name="" if self.unnamed else LABEL,
            record_class_name="transcript",
            search_config=WDKSearchConfig(),
        )


@pytest.fixture(autouse=True)
def _measured(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run(
        *,
        site_id: str,
        wdk_step_id: int,
        positive_controls: list[str] | None = None,
        negative_controls: list[str] | None = None,
    ) -> ControlOutcome:
        del site_id, negative_controls
        return ControlOutcome(
            step_id=wdk_step_id,
            estimated_size=132,
            positive_intersection=2,
            positive_controls_count=len(positive_controls or []),
            positive_recall=2 / 3,
        )

    async def no_export(outcome: ControlOutcome, name: str) -> ControlOutcome:
        del name
        return outcome

    async def no_update(self: TaskProgressEmitter, **kwargs: Any) -> None:
        del self, kwargs

    async def published(
        site_id: str, record_type: str, search_name: str
    ) -> PublishedNames:
        del site_id, record_type, search_name
        return PublishedNames(label=LABEL, parameter_labels={"organism": "Organism"})

    monkeypatch.setattr(control_tests_impl, "run_step_control_tests", run)
    monkeypatch.setattr(control_tests_impl, "attach_control_downloads", no_export)
    monkeypatch.setattr(control_tests_impl, "published_names", published)
    monkeypatch.setattr(TaskProgressEmitter, "update", no_update)


async def test_the_result_names_the_search_the_step_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(control_tests_impl, "get_strategy_api", lambda _site: _Api())

    result = await run_control_tests_on_step_impl(
        context=_context(),
        task_id=uuid4(),
        progress=_emitter(),
        memory_store=None,
        wdk_step_id=STEP_ID,
        positive_controls=["PF3D7_1227900", "PF3D7_0102600", "PF3D7_0213400"],
    )

    assert result["searchName"] == SEARCH
    assert result["stepId"] == STEP_ID
    assert result["positiveIntersection"] == 2
    assert result["targetLabel"] == LABEL
    assert result["parameterLabels"] == {"organism": "Organism"}


async def test_a_refused_step_lookup_leaves_the_name_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        control_tests_impl,
        "get_strategy_api",
        lambda _site: _Api(error=_refused()),
    )

    result = await run_control_tests_on_step_impl(
        context=_context(),
        task_id=uuid4(),
        progress=_emitter(),
        memory_store=None,
        wdk_step_id=STEP_ID,
        positive_controls=["PF3D7_1227900"],
    )

    assert result["searchName"] == ""
    assert result["targetLabel"] == ""
    assert result["parameterLabels"] == {}
    assert result["positiveIntersection"] == 2


async def test_a_step_wdk_does_not_name_falls_back_to_its_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def published(
        site_id: str, record_type: str, search_name: str
    ) -> PublishedNames:
        del site_id, record_type, search_name
        return PublishedNames(label="Combine Gene results")

    monkeypatch.setattr(
        control_tests_impl, "get_strategy_api", lambda _site: _Api(unnamed=True)
    )
    monkeypatch.setattr(control_tests_impl, "published_names", published)

    result = await run_control_tests_on_step_impl(
        context=_context(),
        task_id=uuid4(),
        progress=_emitter(),
        memory_store=None,
        wdk_step_id=STEP_ID,
        positive_controls=["PF3D7_1227900"],
    )

    assert result["targetLabel"] == "Combine Gene results"
