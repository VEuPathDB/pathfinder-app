from __future__ import annotations

import json
from pathlib import Path

import pytest
from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    PHYLETIC_EXPRESSION_SEARCH,
    ParamValue,
    StringValue,
)
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree, walk
from veupathdb.wdk import StrategyAPI, WDKStep, WDKStrategyDetails
from veupathdb_mcp.wdk import WireStep

from strategist.domain.strategy.session import StrategyGraph
from strategist.services.strategies import site_changes
from strategist.services.strategies.sync_state import WDKSyncState

_RECORDED = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "site_values"
        / "phyletic_expressions.json"
    ).read_text()
)
_MORE = _RECORDED["more_proteins"]
_MISSING = _RECORDED["missing_from_strains"]
_LEAF = "step_cd50b9c6"
_WDK_STEP = 227338310
_STRATEGY = 214665440
_TWO_TERMS = "pfal=0 AND tgon>=1 OR pfal=1 AND tgon>=2"
_TEXT_PARAM = "text_expression"


class _Client:
    async def expand_tree_params_to_leaves(
        self, record_type: str, search_name: str, params: dict[str, str]
    ) -> dict[str, str]:
        del record_type, search_name
        return params


async def _decode(
    payload: StrategyAst, api: StrategyAPI, wire: dict[str, WireStep]
) -> None:
    del api
    for node in walk(payload.root):
        node.parameters = {
            name: StringValue(value=value)
            for name, value in wire[node.id].parameters.items()
        }


@pytest.fixture(autouse=True)
def the_recorded_site(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(site_changes, "get_wdk_client", lambda _site: _Client())
    monkeypatch.setattr(site_changes, "canonicalize_synced_parameters", _decode)
    monkeypatch.setattr(site_changes, "get_strategy_api", lambda _site: None)


def _graph(name: str, bound: str) -> StrategyGraph:
    params: dict[str, ParamValue] = {name: StringValue(value=bound)}
    graph = StrategyGraph("g1", "Phyletic Pattern", "orthomcl")
    graph.record_type = "group"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id=_LEAF, search_name=PHYLETIC_EXPRESSION_SEARCH, parameters=params
        )
    )
    graph.recompute_roots()
    return graph


def _site_step(name: str, held: str) -> WDKStep:
    return WDKStep.model_validate(
        {
            "id": _WDK_STEP,
            "searchName": PHYLETIC_EXPRESSION_SEARCH,
            "recordClassName": "group",
            "searchConfig": {"parameters": {name: held}},
        }
    )


async def _held_otherwise(name: str, bound: str, held: str) -> dict[str, str]:
    return await site_changes.values_the_site_holds_otherwise(
        _graph(name, bound).steps[_LEAF], _site_step(name, held), "orthomcl"
    )


@pytest.mark.parametrize("recorded", [_MORE, _MISSING], ids=["more", "missing"])
async def test_the_site_spelling_with_parentheses_holds_no_other_value(
    recorded: dict[str, str],
) -> None:
    assert recorded["bound"] != recorded["site"]

    held = await _held_otherwise(
        PHYLETIC_EXPRESSION_PARAM, recorded["bound"], recorded["site"]
    )

    assert held == {}


@pytest.mark.parametrize(
    ("bound", "site"),
    [
        (_TWO_TERMS, _MORE["site"]),
        (_MORE["bound"].replace("tgon>=112", "tgon>=113"), _MORE["site"]),
        (_MORE["bound"].replace("pfal=0 AND", "pber=0 AND"), _MORE["site"]),
        ("pfal=0 AND tgon>=1 OR pfal>=1", "pfal=0 AND (tgon>=1 OR pfal>=1)"),
        ("pfal=0 OR tgon>=1 AND pfal>=1", "(pfal=0 OR tgon>=1) AND pfal>=1"),
        ("pfal=0 AND tgon>=1", "pfal=0 OR tgon>=1"),
    ],
    ids=[
        "fewer-terms",
        "changed-count",
        "changed-code",
        "and-before-or-regrouped",
        "or-before-and-regrouped",
        "swapped-operator",
    ],
)
async def test_a_different_expression_is_a_value_the_site_holds(
    bound: str, site: str
) -> None:
    held = await _held_otherwise(PHYLETIC_EXPRESSION_PARAM, bound, site)

    assert held == {PHYLETIC_EXPRESSION_PARAM: site}


async def test_a_parameter_of_another_name_is_compared_as_written() -> None:
    site = f"({_TWO_TERMS})"

    held = await _held_otherwise(_TEXT_PARAM, _TWO_TERMS, site)

    assert held == {_TEXT_PARAM: site}


@pytest.mark.parametrize(
    "unread",
    ["pfal=0 AND", "(" * 5000, "pfal>=" + "9" * 5000],
    ids=["grammar", "nesting", "count"],
)
async def test_a_value_that_does_not_parse_is_a_difference_on_either_side(
    unread: str,
) -> None:
    site_side = await _held_otherwise(PHYLETIC_EXPRESSION_PARAM, _TWO_TERMS, unread)
    bound_side = await _held_otherwise(PHYLETIC_EXPRESSION_PARAM, unread, _TWO_TERMS)

    assert (site_side, bound_side) == (
        {PHYLETIC_EXPRESSION_PARAM: unread},
        {PHYLETIC_EXPRESSION_PARAM: _TWO_TERMS},
    )


def _live(held: str) -> WDKStrategyDetails:
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": _STRATEGY,
            "name": "Phyletic Pattern",
            "rootStepId": _WDK_STEP,
            "recordClassName": "group",
            "stepTree": {"stepId": _WDK_STEP},
            "steps": {
                str(_WDK_STEP): _site_step(PHYLETIC_EXPRESSION_PARAM, held).model_dump(
                    by_alias=True, mode="json"
                )
            },
        }
    )


async def _taken(bound: str, held: str) -> tuple[list[str], ParamValue]:
    graph = _graph(PHYLETIC_EXPRESSION_PARAM, bound)
    edits = await site_changes.take_what_the_site_holds(
        graph=graph,
        sync_state=WDKSyncState(
            wdk_step_ids={_LEAF: _WDK_STEP}, wdk_strategy_id=_STRATEGY
        ),
        site_id="orthomcl",
        live=_live(held),
    )
    return edits.valued, graph.steps[_LEAF].parameters[PHYLETIC_EXPRESSION_PARAM]


async def test_a_read_of_the_site_spelling_keeps_the_bound_spelling() -> None:
    assert await _taken(_MORE["bound"], _MORE["site"]) == (
        [],
        StringValue(value=_MORE["bound"]),
    )


async def test_a_read_of_a_different_expression_takes_it() -> None:
    assert await _taken("pfal=0 AND tgon>=1", _MORE["site"]) == (
        [_LEAF],
        StringValue(value=_MORE["site"]),
    )
