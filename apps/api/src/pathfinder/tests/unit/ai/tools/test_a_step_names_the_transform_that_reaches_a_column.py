"""A step whose records count by no column names each transform that reaches a
countable column, from the site's catalog, on the turn's recorded calls."""

from __future__ import annotations

from typing import NamedTuple

import pytest
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKRecordType
from veupathdb_mcp.wdk import StepColumn, StepColumns, transforms_from

from pathfinder.ai.lead.turn_contract import LeadResponse, reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.ai.tools.standalone.step_tally import StepColumnPage, step_columns
from pathfinder.domain.column_reach import ReachedColumn, TransformReach
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.tally_facts import TallyFact
from pathfinder.services.experiment import step_tally
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.orthomcl_record_classes import (
    recorded_orthomcl_record_types,
)
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned


class RecordedCall(NamedTuple):
    name: str
    countable_only: bool
    offset: int


GROUP_STEP = 227288240
TURN_ONE_CALL = RecordedCall(name="organism", countable_only=True, offset=0)
TURN_TWO_CALL = RecordedCall(name="", countable_only=True, offset=0)
TURN_ONE_REPLY = (
    "The strategy correctly defines singleton groups as groups containing exactly "
    "one protein and returns the singleton groups. However, it does not restrict "
    "the records to Plasmodium or provide species-level counts, so it cannot "
    "determine which Plasmodium species has the most singleton genes. The site's "
    "available result fields did not expose the ranking needed for that "
    "comparison. The strategy link is available beside this reply if you want to "
    "inspect the singleton-group result."
)
FROM_GROUPS = TransformReach(
    search_name="FromGroups",
    display_name="Transform Groups to Proteins",
    record_type="sequence",
    countable=1,
    columns=[ReachedColumn(name="abbreviation", display_name="Taxon Code")],
)


def _singleton_groups() -> StrategySession:
    session = StrategySession(site_id="orthomcl")
    graph = StrategyGraph("g1", "singleton groups", "orthomcl")
    graph.record_type = "group"
    graph.steps = flatten_tree(
        StrategyStepNode(id="step_88b8197d", search_name="GroupsBySequenceCount")
    )
    graph.steps["step_88b8197d"].record_class = "group"
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(wdk_step_ids={"step_88b8197d": GROUP_STEP})
    return session


def _group_columns(record_types: list[WDKRecordType]) -> StepColumns:
    group = next(r for r in record_types if r.url_segment == "group")
    return StepColumns(
        step_id=GROUP_STEP,
        record_type="group",
        search_name="GroupsBySequenceCount",
        columns=tuple(
            StepColumn(
                name=a.name,
                display_name=a.display_name or a.name,
                data_type=a.column_data_type,
                countable=a.column_data_type in ("STRING", "NUMBER")
                and "byValue" in a.tools.reports,
            )
            for a in group.attributes or []
        ),
        transforms=transforms_from(record_types, "group"),
    )


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    record_types = recorded_orthomcl_record_types()
    listed_for: list[int] = []

    async def list_step_columns(site_id: str, step_id: int) -> StepColumns:
        assert site_id == "orthomcl"
        listed_for.append(step_id)
        return _group_columns(record_types)

    async def raw_record_types(site_id: str) -> list[WDKRecordType]:
        assert site_id == "orthomcl"
        return record_types

    monkeypatch.setattr(step_tally, "list_step_columns", list_step_columns)
    monkeypatch.setattr(step_tally, "get_raw_record_types", raw_record_types)
    return listed_for


async def test_the_recorded_column_reads_name_the_transform_to_proteins(
    served: list[int],
) -> None:
    ctx = lead_run_context(site_id="orthomcl", strategy_session=_singleton_groups())

    pages = [
        returned(await step_columns(ctx, GROUP_STEP, *call), StepColumnPage)
        for call in (TURN_ONE_CALL, TURN_TWO_CALL)
    ]

    assert served == [GROUP_STEP, GROUP_STEP]
    assert [
        (p.record_type, p.total, p.countable, p.reach, p.transforms) for p in pages
    ] == [
        ("group", 0, 0, "transform", [FROM_GROUPS]),
        ("group", 0, 0, "transform", [FROM_GROUPS]),
    ]


async def test_the_recorded_reply_over_the_read_is_refused_naming_the_transform(
    served: list[int],
) -> None:
    ctx = lead_run_context(site_id="orthomcl", strategy_session=_singleton_groups())
    await step_columns(ctx, GROUP_STEP, *TURN_ONE_CALL)

    found = {
        m.kind: m.sentence
        for m in reconcile(
            LeadResponse(prose=TURN_ONE_REPLY),
            turn_record(ctx),
        )
    }

    assert served == [GROUP_STEP]
    assert found["unfollowed_reach"].startswith(
        "step_columns found no countable column on step 227288240 (group records) "
        "for this count. FromGroups (Transform Groups to Proteins) reaches sequence "
        "records, which count by abbreviation (Taxon Code)."
    )


async def test_the_asked_name_does_not_narrow_what_a_transform_reaches(
    served: list[int],
) -> None:
    ctx = lead_run_context(site_id="orthomcl", strategy_session=_singleton_groups())

    page = returned(
        await step_columns(ctx, GROUP_STEP, name="pfam", countable_only=True),
        StepColumnPage,
    )

    assert served == [GROUP_STEP]
    assert page.transforms == [FROM_GROUPS]


async def test_a_reach_stands_unfollowed_until_a_tally_counts(
    served: list[int],
) -> None:
    ctx = lead_run_context(site_id="orthomcl", strategy_session=_singleton_groups())
    markers = ctx.deps.state.turn_markers

    await step_columns(ctx, GROUP_STEP, *TURN_ONE_CALL)
    unfollowed = markers.unfollowed_reach()
    markers.record_tally(
        TallyFact(
            id="orthomcl-step-1-abbreviation",
            title="Sequences by Taxon Code",
            record_noun="sequence",
            total=523795,
            distinct=1,
        )
    )

    assert served == [GROUP_STEP]
    assert unfollowed is not None
    assert (unfollowed.wdk_step_id, unfollowed.transforms) == (
        GROUP_STEP,
        [FROM_GROUPS],
    )
    assert markers.unfollowed_reach() is None
