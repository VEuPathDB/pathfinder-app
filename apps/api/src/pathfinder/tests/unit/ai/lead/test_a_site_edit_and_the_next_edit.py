"""A value set on VEuPathDB itself, then a turn, then an edit in chat.

The turn entry reads the site under the thread's write lock, so the stored
graph holds the site's value, the spec replays it like any change written
outside the thread, and the edit after it sends it on.
"""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.services.strategies import step_wdk_push
from pathfinder.services.strategies.step_push_planner import (
    PatchAction,
    SkipAction,
    plan_step_pushes,
)
from pathfinder.services.strategies.step_wdk_push import push_steps_with_plan
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    PROTEOME,
    PROTEOME_PARAM,
    canvas_flips,
    canvas_sets,
    with_the_percentile,
    with_the_proteome,
)
from pathfinder.tests.unit.ai.lead._disagreement_facts import (
    OpFacts,
    committed_facts,
    facts_of,
    spec_facts,
)
from pathfinder.tests.unit.ai.lead._disagreement_site import (
    TheSite,
    install_the_site,
    site_sets,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    ROOT,
    STAGE,
    STAGE_PERCENTILE,
    STAGE_TIMEPOINT,
    SURFACE,
    DisagreementThread,
    built_spec,
    built_tree,
    declared,
    kept,
    recorded,
    session_holding,
)
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import StubAPI


def _thread(monkeypatch: pytest.MonkeyPatch) -> tuple[DisagreementThread, TheSite]:
    thread = DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )
    return thread, install_the_site(thread)


async def _the_writes(
    thread: DisagreementThread, site: TheSite, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[str, int, dict[str, str] | None]]:
    """The WDK writes the production push sends for the edit the thread made."""
    before = site.pushed
    after = thread.graph.to_strategy_ast()
    assert after is not None
    api = StubAPI()

    async def _nothing_incomplete(*_args: Any, **_kwargs: Any) -> set[str]:
        return set()

    monkeypatch.setattr(step_wdk_push, "get_strategy_api", lambda _site: api)
    monkeypatch.setattr(step_wdk_push, "_validate_plan_params", _nothing_incomplete)
    plan = plan_step_pushes(old_ast=before, new_ast=after, existing_wdk_ids=site.ids)
    assert {entry.step_id: entry.action for entry in plan} == {
        SURFACE: SkipAction(),
        STAGE: PatchAction(search_config=True, name=False),
        ROOT: SkipAction(),
    }
    await push_steps_with_plan(
        thread.graph, WDKSyncState(wdk_step_ids=site.ids), "plasmodb", plan
    )
    return [
        (call.name, call.kwargs["step_id"], call.kwargs.get("parameters"))
        for call in api.calls
    ]


async def test_a_chat_edit_after_a_site_edit_sends_the_sites_value_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The PUT carries the site's value for the parameter the edit did not name."""
    thread, site = _thread(monkeypatch)
    site_sets(site, STAGE, timepoint=NumberValue(value=48))
    await thread.next_turn()
    site.remember_the_push(thread)
    thread.frames(
        with_the_percentile(90),
        declared=[*kept(SURFACE), *declared("changed", STAGE)],
    )

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert committed_facts(thread.committed) == [
        OpFacts(
            kind="updateStepParams",
            step_id=STAGE,
            parameters={STAGE_PERCENTILE: "90"},
        )
    ]
    assert [
        (c.criterion_id, c.disposition, c.changed_params)
        for c in delta.diff.changes
        if c.disposition != "kept"
    ] == [(STAGE, "changed", {STAGE_PERCENTILE: "90"})]
    assert await _the_writes(thread, site, monkeypatch) == [
        (
            "update_step_search_config",
            site.ids[STAGE],
            {STAGE_PERCENTILE: "90", STAGE_TIMEPOINT: "48"},
        )
    ]
    assert site.stored_writes == 1


async def test_a_site_value_and_a_canvas_value_on_one_step_both_reach_the_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread, site = _thread(monkeypatch)
    site_sets(site, STAGE, timepoint=NumberValue(value=48))
    canvas_sets(thread.graph, STAGE, min_expression_percentile=NumberValue(value=90))
    await thread.next_turn()
    untouched = facts_of(thread.facts(), SURFACE, STAGE, ROOT)
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert facts_of(thread.facts(), SURFACE, STAGE, ROOT) == untouched
    assert spec_facts(thread.spec) == {
        SURFACE: {},
        STAGE: {STAGE_PERCENTILE: "90", STAGE_TIMEPOINT: "48"},
        PROTEOME: {PROTEOME_PARAM: "2"},
    }
    assert delta.preserved_step_ids == [SURFACE, STAGE]


async def test_a_site_value_stands_beside_a_canvas_flip_through_the_next_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread, site = _thread(monkeypatch)
    site_sets(site, STAGE, timepoint=NumberValue(value=48))
    canvas_flips(thread.graph, ROOT, CombineOp.UNION)
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert thread.graph.steps[ROOT].operator is CombineOp.UNION
    assert spec_facts(thread.spec)[STAGE] == {
        STAGE_PERCENTILE: "80",
        STAGE_TIMEPOINT: "48",
    }
    assert delta.diff.render() == (
        "kept 2, changed 0, added 1, dropped 0, structure rewired"
    )


async def test_a_site_that_moved_nothing_leaves_the_thread_as_it_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread, site = _thread(monkeypatch)
    before = thread.facts()

    site_sets(site, STAGE, timepoint=NumberValue(value=40))
    await thread.next_turn()

    assert (site.reads, site.stored_writes) == (1, 0)
    assert thread.facts() == before
    assert thread.spec == built_spec()


async def test_a_site_that_does_not_answer_leaves_the_stored_graph_and_runs_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread, site = _thread(monkeypatch)
    before = thread.facts()
    site_sets(site, STAGE, timepoint=NumberValue(value=48))
    site.refuse = OSError("the site is not answering")

    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))
    delta = await thread.edit()

    assert (site.reads, site.stored_writes) == (1, 0)
    assert facts_of(thread.facts(), SURFACE, STAGE, ROOT) == facts_of(
        before, SURFACE, STAGE, ROOT
    )
    assert isinstance(delta, EditDelta)
    assert spec_facts(thread.spec)[STAGE] == {
        STAGE_PERCENTILE: "80",
        STAGE_TIMEPOINT: "40",
    }
