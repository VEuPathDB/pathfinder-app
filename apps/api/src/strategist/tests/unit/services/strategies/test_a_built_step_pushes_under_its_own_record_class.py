"""A commit pushes each step under the record class its search is listed under,
so a transform reads its own input parameters from the catalog."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from veupathdb.domain import SearchContext
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb_mcp.catalog import ValidatedParams

from strategist.services.strategies import commit_tree, record_classes
from strategist.services.strategies.commit_tree import CommitTarget, CommittedTree
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.wdk_write_stubs import skip_the_tree_put

from ._counting_strategy_api import CountingStrategyAPI

_LISTED_UNDER = {
    "GroupsByPhyleticPattern": "group",
    "FromGroups": "sequence",
    "ByTaxonomy": "sequence",
}


def _recording(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[tuple[str, str]], CountingStrategyAPI]:
    validated: list[tuple[str, str]] = []
    api = CountingStrategyAPI()

    async def _validate(ctx: SearchContext, **_kwargs: object) -> ValidatedParams:
        validated.append((ctx.search_name, ctx.record_type))
        return ValidatedParams(params={}, record_class=_LISTED_UNDER[ctx.search_name])

    async def _resolver(_site_id: str) -> Callable[[str], Awaitable[str | None]]:
        async def _listed_under(search_name: str) -> str | None:
            return _LISTED_UNDER.get(search_name)

        return _listed_under

    monkeypatch.setattr(commit_tree, "validate_parameters", _validate)
    monkeypatch.setattr(commit_tree, "get_strategy_api", lambda _site: api)
    monkeypatch.setattr(record_classes, "make_record_type_resolver", _resolver)
    skip_the_tree_put(monkeypatch)
    return validated, api


async def _commit(root: StrategyStepNode) -> CommittedTree:
    return await commit_tree.commit_tree(
        site_id="orthomcl",
        steps=flatten_tree(root),
        root_id=root.id,
        old=None,
        sync_state=WDKSyncState(),
        target=CommitTarget(name="groups", description=""),
    )


async def test_each_step_of_an_orthomcl_build_pushes_under_its_own_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validated, api = _recording(monkeypatch)

    await _commit(
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

    assert validated == [
        ("GroupsByPhyleticPattern", "group"),
        ("FromGroups", "sequence"),
        ("ByTaxonomy", "sequence"),
    ]
    assert [(c.name, c.kwargs["record_type"]) for c in api.calls] == [
        ("create_step", "group"),
        ("create_transform_step", "sequence"),
        ("create_step", "sequence"),
        ("create_combined_step", "sequence"),
    ]


async def test_a_build_step_the_site_lists_under_no_class_is_not_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validated, api = _recording(monkeypatch)

    committed = await _commit(StrategyStepNode(id="lost", search_name="Unlisted"))

    assert (validated, api.calls, [f.error for f in committed.failures]) == (
        [],
        [],
        [
            (
                "The site lists no record type for Unlisted, so Strategist cannot "
                "address the step and did not send it."
            )
        ],
    )
