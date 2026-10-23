from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    ColocationParams,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.wdk import WDKSearchConfig, WDKStep, WDKStepTree, WDKStrategyDetails

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies import record_classes, site_changes
from pathfinder.services.strategies.record_classes import tree_record_class_refusal
from pathfinder.services.strategies.step_push_planner import (
    CreateAction,
    StepPushPlan,
)
from pathfinder.services.strategies.step_wdk_push import push_steps_with_plan
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    install_stub_api,
)

_GROUPS_STEP = 227284900
_LISTED = {
    "GroupsByPhyleticPattern": "group",
    "GenesByTaxon": "transcript",
    "GenesBySpanLogic": "transcript",
    "SnpsByLocation": "snp",
}


def _serve_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _resolver(_site_id: str) -> Callable[[str], Awaitable[str | None]]:
        async def _listed_under(search_name: str) -> str | None:
            return _LISTED.get(search_name)

        return _listed_under

    monkeypatch.setattr(record_classes, "make_record_type_resolver", _resolver)


def _groups_in_a_gene_strategy(search_name: str) -> StrategyGraph:
    graph = StrategyGraph("g1", "mammal groups", "orthomcl")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_groups",
            search_name=search_name,
            parameters={"phyletic_expression": StringValue(value="MAMM>=1T")},
        )
    )
    graph.recompute_roots()
    return graph


def _live(record_class_name: str | None, search_name: str) -> WDKStrategyDetails:
    return WDKStrategyDetails(
        strategy_id=330534153,
        name="mammal groups",
        root_step_id=_GROUPS_STEP,
        step_tree=WDKStepTree(step_id=_GROUPS_STEP),
        steps={
            str(_GROUPS_STEP): WDKStep(
                id=_GROUPS_STEP,
                search_name=search_name,
                search_config=WDKSearchConfig(
                    parameters={"phyletic_expression": "MAMM>=2T"}
                ),
                record_class_name=record_class_name,
            )
        },
    )


@pytest.mark.parametrize(
    ("record_class_name", "search_name", "decoded_under"),
    [
        ("group", "GroupsByPhyleticPattern", ["group"]),
        (None, "GroupsByPhyleticPattern", ["group"]),
        (None, "Unlisted", []),
    ],
)
async def test_a_site_edit_is_decoded_under_the_steps_own_class(
    monkeypatch: pytest.MonkeyPatch,
    record_class_name: str | None,
    search_name: str,
    decoded_under: list[str],
) -> None:
    _serve_listing(monkeypatch)
    asked: list[str] = []

    async def _decoded(
        _step_id: str,
        _search_name: str,
        _wire: object,
        record_type: str,
        _site_id: str,
    ) -> dict[str, ParamValue]:
        asked.append(record_type)
        return {}

    monkeypatch.setattr(site_changes, "_decoded", _decoded)

    await site_changes._take_the_sites_values(
        _groups_in_a_gene_strategy(search_name),
        {_GROUPS_STEP: "step_groups"},
        _live(record_class_name, search_name),
        None,
        "orthomcl",
    )

    assert asked == decoded_under


def _colocation(primary: StrategyStepNode) -> StrategyStepNode:
    return StrategyStepNode(
        id="step_near",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.COLOCATE,
        colocation_params=ColocationParams(),
        primary_input=primary,
        secondary_input=StrategyStepNode(id="step_snps", search_name="SnpsByLocation"),
    )


def _join(left: StrategyStepNode, right: StrategyStepNode) -> StrategyStepNode:
    return StrategyStepNode(
        id="step_join",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=left,
        secondary_input=right,
    )


def _groups() -> StrategyStepNode:
    return StrategyStepNode(id="step_groups", search_name="GroupsByPhyleticPattern")


def _genes() -> StrategyStepNode:
    return StrategyStepNode(id="step_genes", search_name="GenesByTaxon")


async def test_a_colocation_returns_the_class_its_own_search_is_listed_under(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve_listing(monkeypatch)
    near_groups = _colocation(_groups())

    refusals = [
        await tree_record_class_refusal("plasmodb", _join(near_groups, _genes()), {}),
        await tree_record_class_refusal(
            "plasmodb", _join(_colocation(_genes()), _groups()), {}
        ),
    ]

    assert refusals[0] is None
    assert refusals[1] is not None
    assert refusals[1].startswith(
        "The INTERSECT of (step_genes COLOCATE step_snps) (Genes) and "
        "step_groups (group) joins two record types."
    )


async def test_a_colocation_over_groups_is_posted_under_its_own_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api: StubAPI = install_stub_api(monkeypatch)
    _serve_listing(monkeypatch)
    graph = StrategyGraph("g1", "groups near snps", "plasmodb")
    graph.steps = flatten_tree(_colocation(_groups()))
    graph.recompute_roots()
    plan = [
        StepPushPlan(step_id=step_id, action=CreateAction(), reason="new")
        for step_id in ("step_groups", "step_snps", "step_near")
    ]

    outcome = await push_steps_with_plan(graph, WDKSyncState(), "plasmodb", plan)

    assert (outcome.failed, graph.steps["step_near"].record_class) == (
        [],
        "transcript",
    )
    assert [(c.name, c.kwargs["record_type"]) for c in api.calls] == [
        ("create_step", "group"),
        ("create_step", "snp"),
        ("create_transform_step", "transcript"),
    ]
