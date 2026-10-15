"""A declarative build pushes each step under the record class its search is
listed under, so a transform reads its own input parameters from the catalog."""

from __future__ import annotations

import pytest
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StepValidation,
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.services.strategies import spec_build
from pathfinder.services.strategies.sync_state import WDKSyncState

_LISTED_UNDER = {
    "GroupsByPhyleticPattern": "group",
    "FromGroups": "sequence",
    "ByTaxonomy": "sequence",
}


async def _validate(ctx: SearchContext, **_kwargs: object) -> ValidatedParams:
    return ValidatedParams(params={}, record_class=_LISTED_UNDER[ctx.search_name])


def _recording(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    pushed: list[tuple[str, str]] = []

    async def _push(
        *,
        sync_state: WDKSyncState,
        step: StrategyStep,
        site_id: str,
        record_type: str,
        search_name: str,
        parameters: dict[str, ParamValue],
    ) -> tuple[int | None, StepValidation | None, str | None]:
        del site_id, search_name, parameters
        pushed.append((step.id, record_type))
        sync_state.wdk_step_ids[step.id] = 1000 + len(pushed)
        return sync_state.wdk_step_ids[step.id], None, None

    monkeypatch.setattr(spec_build, "validate_parameters", _validate)
    monkeypatch.setattr(spec_build, "push_step_to_wdk", _push)
    return pushed


async def test_each_step_of_an_orthomcl_build_pushes_under_its_own_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pushed = _recording(monkeypatch)
    steps = flatten_tree(
        StrategyStepNode(
            id="and",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(
                id="proteins",
                search_name="FromGroups",
                primary_input=StrategyStepNode(
                    id="pattern", search_name="GroupsByPhyleticPattern"
                ),
            ),
            secondary_input=StrategyStepNode(id="taxon", search_name="ByTaxonomy"),
        )
    )
    order = ["pattern", "proteins", "taxon", "and"]

    await spec_build._push_tree_to_wdk(
        nodes=[steps[step_id] for step_id in order],
        graph_record_type="transcript",
        site_id="orthomcl",
        sync_state=WDKSyncState(),
        outcome=BuildOutcome(),
    )

    assert pushed == [
        ("pattern", "group"),
        ("proteins", "sequence"),
        ("taxon", "sequence"),
        ("and", "sequence"),
    ]
