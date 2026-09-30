"""Which genes a built step holds is a read of its primary keys, and saves nothing."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.wdk import (
    StrategyAPI,
    WDKAnswer,
    WDKFilterValue,
    WDKRecordInstance,
    WDKSearchConfig,
    WDKSortSpec,
    WDKStep,
    WDKStepTree,
)

from pathfinder.ai.tools.standalone import gene_sets, results, step_ids
from pathfinder.ai.tools.standalone.step_ids import StepGeneIds, read_step_ids
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.gene_sets import step_genes
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context, summary_of

_ROOT_WDK_STEP = 441031123
_STEP_GENES = ["PF3D7_0304600", "PF3D7_1133400", "PF3D7_0930300"]


def _transcript(gene_id: str) -> WDKRecordInstance:
    return WDKRecordInstance.model_validate(
        {
            "displayName": f"{gene_id}.1",
            "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
            "id": [
                {"name": "source_id", "value": f"{gene_id}.1"},
                {"name": "gene_source_id", "value": gene_id},
            ],
        }
    )


class _Reports(StrategyAPI):
    """Answers the standard report of one step, recording each request."""

    def __init__(self) -> None:
        self.asked: list[tuple[int, list[str] | None, dict[str, int] | None]] = []

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name="GenesByTaxon",
            search_config=WDKSearchConfig(),
            record_class_name="transcript",
        )

    async def get_step_records(
        self,
        step_id: int,
        attributes: list[str] | None = None,
        tables: list[str] | None = None,
        pagination: dict[str, int] | None = None,
        sorting: list[WDKSortSpec] | None = None,
        *,
        view_filters: Sequence[WDKFilterValue] | None = None,
    ) -> WDKAnswer:
        del tables, sorting, view_filters
        self.asked.append((step_id, attributes, pagination))
        window = pagination or {"offset": 0, "numRecords": len(_STEP_GENES)}
        start = window["offset"]
        page = _STEP_GENES[start : start + window["numRecords"]]
        return WDKAnswer.model_validate(
            {
                "meta": {"totalCount": len(_STEP_GENES), "recordClassName": "x"},
                "records": [_transcript(g).model_dump(by_alias=True) for g in page],
            }
        )


@pytest.fixture
def reports(monkeypatch: pytest.MonkeyPatch) -> _Reports:
    api = _Reports()
    monkeypatch.setattr(step_genes, "get_strategy_api", lambda _site_id: api)
    return api


def _built_session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    session.graph = StrategyGraph(graph_id="g1", name="antigens", site_id="plasmodb")
    session.sync_state = WDKSyncState(
        wdk_step_ids={"step_root": _ROOT_WDK_STEP}, wdk_strategy_id=330531493
    )
    return session


async def test_the_ids_come_from_the_steps_primary_keys(reports: _Reports) -> None:
    session = _built_session()
    ctx = agent_run_context(strategy_session=session)

    result = await read_step_ids(ctx, wdk_step_id=_ROOT_WDK_STEP, limit=2)

    read = returned(result, StepGeneIds)
    seed = results.step_sample_seed(session, _ROOT_WDK_STEP)
    picked = [_STEP_GENES[o] for o in results.spread_offsets(3, 2, seed=seed)]
    assert (read.gene_ids, read.total, read.complete) == (picked, 3, False)
    assert [asked[1] for asked in reports.asked] == [["primary_key"]] * len(
        reports.asked
    )
    assert summary_of(result).model_dump(by_alias=True)["data"]["summary"] == (
        "2 of 3 genes"
    )


async def test_every_gene_read_is_a_complete_answer(reports: _Reports) -> None:
    ctx = agent_run_context(strategy_session=_built_session())

    read = returned(await read_step_ids(ctx, wdk_step_id=_ROOT_WDK_STEP), StepGeneIds)

    assert (read.gene_ids, read.complete) == (_STEP_GENES, True)
    assert len(reports.asked) == 1


async def test_a_step_this_strategy_did_not_build_is_refused(
    reports: _Reports,
) -> None:
    ctx = agent_run_context(strategy_session=_built_session())

    with pytest.raises(ModelRetry) as refused:
        await read_step_ids(ctx, wdk_step_id=227253270)

    assert f"The built steps: {_ROOT_WDK_STEP}." in str(refused.value)
    assert reports.asked == []


_LEAF_WDK_STEP = 441125223


async def test_a_read_that_names_no_step_reads_the_root(reports: _Reports) -> None:
    session = _built_session()
    session.sync_state = WDKSyncState(
        wdk_step_ids={"step_root": _ROOT_WDK_STEP, "step_d2536be6": _LEAF_WDK_STEP},
        wdk_strategy_id=330531493,
        wdk_step_tree=WDKStepTree(
            step_id=_ROOT_WDK_STEP, primary_input=WDKStepTree(step_id=_LEAF_WDK_STEP)
        ),
    )

    read = returned(
        await read_step_ids(agent_run_context(strategy_session=session)), StepGeneIds
    )

    assert (read.wdk_step_id, reports.asked[0][0]) == (_ROOT_WDK_STEP, _ROOT_WDK_STEP)


async def test_a_read_that_names_no_step_before_a_push_is_refused(
    reports: _Reports,
) -> None:
    session = StrategySession(site_id="plasmodb")

    with pytest.raises(ModelRetry) as refused:
        await read_step_ids(agent_run_context(strategy_session=session))

    assert str(refused.value) == (
        "This conversation's strategy has no built root yet, so no step holds genes "
        "to read."
    )
    assert reports.asked == []


def test_the_read_saves_nothing_and_the_save_is_never_a_read() -> None:
    described: dict[str, Any] = {
        "read": read_step_ids.__doc__ or "",
        "save": gene_sets.save_gene_set.__doc__ or "",
    }

    assert "It saves nothing" in described["read"]
    assert "A save is never a read: ``read_step_ids``" in " ".join(
        described["save"].split()
    )
    assert step_ids.STEP_IDS_CAP == 5000


async def test_the_lead_reads_the_same_ids_on_its_own_context(
    reports: _Reports,
) -> None:
    session = _built_session()
    reads = [
        returned(
            await read_step_ids(context, wdk_step_id=_ROOT_WDK_STEP, limit=1),
            StepGeneIds,
        )
        for context in (
            lead_run_context(strategy_session=session),
            agent_run_context(strategy_session=session),
        )
    ]

    assert [(r.gene_ids, r.total) for r in reads] == [(reads[1].gene_ids, 3)] * 2
    assert len(reads[0].gene_ids) == 1


class _KeylessFirstRecord(_Reports):
    """A report whose first record carries no primary key value."""

    async def get_step_records(
        self,
        step_id: int,
        attributes: list[str] | None = None,
        tables: list[str] | None = None,
        pagination: dict[str, int] | None = None,
        sorting: list[WDKSortSpec] | None = None,
        *,
        view_filters: Sequence[WDKFilterValue] | None = None,
    ) -> WDKAnswer:
        del tables, sorting, view_filters
        self.asked.append((step_id, attributes, pagination))
        rows = [
            {
                "displayName": "",
                "recordClassName": "x",
                "id": [{"name": "source_id", "value": ""}],
            },
            *(_transcript(g).model_dump(by_alias=True) for g in _STEP_GENES),
        ]
        window = pagination or {"offset": 0, "numRecords": len(rows)}
        page = rows[window["offset"] : window["offset"] + window["numRecords"]]
        return WDKAnswer.model_validate(
            {"meta": {"totalCount": len(rows), "recordClassName": "x"}, "records": page}
        )


async def test_each_page_starts_after_the_records_the_last_one_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _KeylessFirstRecord()
    monkeypatch.setattr(step_genes, "get_strategy_api", lambda _site_id: api)

    read = await step_genes.first_step_gene_ids(
        "plasmodb", _ROOT_WDK_STEP, limit=5000, page_size=2
    )

    assert read.gene_ids == _STEP_GENES
    assert [asked[2] for asked in api.asked] == [
        {"offset": 0, "numRecords": 2},
        {"offset": 2, "numRecords": 2},
    ]


async def test_each_gene_read_names_the_step_it_was_listed_from(
    reports: _Reports,
) -> None:
    ctx = lead_run_context(strategy_session=_built_session())

    await read_step_ids(ctx, wdk_step_id=_ROOT_WDK_STEP)

    assert ctx.deps.turn_markers.listings == {_ROOT_WDK_STEP: _STEP_GENES}
