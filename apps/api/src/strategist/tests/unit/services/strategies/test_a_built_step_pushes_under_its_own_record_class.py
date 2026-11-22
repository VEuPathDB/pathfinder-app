"""A declarative build pushes each step under the record class its search is
listed under, so a transform reads its own input parameters from the catalog."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

import pytest
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StepKind,
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.wdk import StrategyAPI
from veupathdb_mcp.catalog import ValidatedParams

from strategist.domain.strategy.build_outcome import BuildOutcome, StepPushFailure
from strategist.services.strategies import record_classes, spec_build
from strategist.services.strategies.sync_state import WDKSyncState

_LISTED_UNDER = {
    "GroupsByPhyleticPattern": "group",
    "FromGroups": "sequence",
    "ByTaxonomy": "sequence",
}


def _recording(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    pushed: list[tuple[str, str]] = []

    async def _validate(ctx: SearchContext, **_kwargs: object) -> ValidatedParams:
        pushed.append((ctx.search_name, ctx.record_type))
        return ValidatedParams(params={}, record_class=_LISTED_UNDER[ctx.search_name])

    async def _resolver(_site_id: str) -> Callable[[str], Awaitable[str | None]]:
        async def _listed_under(search_name: str) -> str | None:
            return _LISTED_UNDER.get(search_name)

        return _listed_under

    async def _push(
        api: StrategyAPI,
        sync_state: WDKSyncState,
        step: StrategyStep,
        record_type: str,
        parameters: Mapping[str, ParamValue],
    ) -> StepPushFailure | None:
        del api, parameters
        pushed.append((step.id, record_type))
        sync_state.wdk_step_ids[step.id] = 1000 + len(pushed)
        return None

    monkeypatch.setattr(spec_build, "validate_parameters", _validate)
    monkeypatch.setattr(spec_build, "pushed_step", _push)
    monkeypatch.setattr(record_classes, "make_record_type_resolver", _resolver)
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
        held={},
        site_id="orthomcl",
        sync_state=WDKSyncState(),
        outcome=BuildOutcome(),
    )

    assert pushed == [
        ("GroupsByPhyleticPattern", "group"),
        ("pattern", "group"),
        ("FromGroups", "sequence"),
        ("proteins", "sequence"),
        ("ByTaxonomy", "sequence"),
        ("taxon", "sequence"),
        ("and", "sequence"),
    ]


async def test_a_build_step_the_site_lists_under_no_class_is_not_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pushed = _recording(monkeypatch)
    outcome = BuildOutcome()

    await spec_build._push_tree_to_wdk(
        nodes=[StrategyStep(id="lost", kind=StepKind.SEARCH, search_name="Unlisted")],
        held={},
        site_id="orthomcl",
        sync_state=WDKSyncState(),
        outcome=outcome,
    )

    assert (pushed, [f.error for f in outcome.failed_steps]) == (
        [],
        [
            (
                "The site lists no record type for Unlisted, so Strategist cannot "
                "address the step and did not send it."
            )
        ],
    )
