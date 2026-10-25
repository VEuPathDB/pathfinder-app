"""A strategy built on a computed snapshot carries the snapshot's note as its
description on the site."""

from __future__ import annotations

from datetime import date

import pytest
from veupathdb.domain.parameters import InputDatasetValue, StringValue

from pathfinder.domain.strategy.computed_groups import (
    SNAPSHOT_NOTE,
    HeldComparison,
    snapshot_note,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import spec_build, sync
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.spec_build import build_strategy_from_spec
from pathfinder.tests._support.computed_comparison import held_comparison
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import install_stub_api, leaf
from pathfinder.tests.unit.domain.strategy.test_a_comparison_names_its_breakdown import (
    _PATTERN,
)

_DATASET = "202394260"


def _spec(dataset_id: str) -> OperationalSpec:
    return OperationalSpec(
        criteria=[
            Criterion(
                id="c_groups",
                text="groups with more proteins per genome in the left set",
                search_name="GroupsByNameList",
                resolved_params={
                    "group_names": BoundValue(
                        value=InputDatasetValue(dataset_id=dataset_id),
                        source="chosen",
                    )
                },
            )
        ]
    )


def _held() -> dict[str, HeldComparison]:
    held = held_comparison(_PATTERN, date(2026, 10, 25)).model_copy(
        update={"dataset_id": _DATASET}
    )
    return {held.handle: held}


def test_a_spec_bound_to_a_saved_comparison_takes_the_note() -> None:
    assert [snapshot_note(_held(), _spec(d)) for d in (_DATASET, "1")] == [
        SNAPSHOT_NOTE,
        None,
    ]


async def _created(monkeypatch: pytest.MonkeyPatch, note: str | None) -> list[object]:
    api = install_stub_api(monkeypatch)

    async def _quiet(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(spec_build, "persist_strategy_ast_to_conversation", _quiet)
    monkeypatch.setattr(spec_build, "defer_the_gene_set_refresh", _quiet)
    monkeypatch.setattr(
        spec_build, "sync_strategy_for_site", sync.sync_strategy_for_site
    )
    graph = StrategyGraph("g1", "Groups", "plasmodb")
    graph.record_type = "transcript"
    session = StrategySession(site_id="plasmodb")
    session.graph = graph
    await build_strategy_from_spec(
        deps=StrategyMutationContext(
            site_id="plasmodb", strategy_session=session, wdk_description=note
        ),
        root=leaf("step_a", {"organism": StringValue(value="P. falciparum 3D7")}),
    )
    return [call.kwargs["description"] for call in api.named("create_strategy")]


async def test_the_build_sends_the_note_as_the_strategy_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert await _created(monkeypatch, SNAPSHOT_NOTE) == [SNAPSHOT_NOTE]


async def test_a_build_without_a_note_sends_no_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert await _created(monkeypatch, None) == [None]
