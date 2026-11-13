from __future__ import annotations

import json
from pathlib import Path

import pytest
from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    PHYLETIC_EXPRESSION_SEARCH,
    StringValue,
)
from veupathdb.domain.strategy import StepKind, StrategyAst, StrategyStep, walk
from veupathdb.wdk import StrategyAPI, WDKStrategyDetails
from veupathdb_mcp.wdk import WireStep

from strategist.ai.lead.verify_checks import _bound_values, _judged
from strategist.domain.site_checks import SiteCheck
from strategist.domain.strategy.session import StrategyGraph
from strategist.services.strategies import site_changes
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests.fixtures.builders import add_step_to_graph

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
_STEP = "step_cd50b9c6"
_WDK_STEP = 227338310
_STRATEGY = 214665440
_RESULT = 3896


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


async def _check(bound: str, held: str) -> SiteCheck:
    graph = StrategyGraph("g1", "Phyletic Pattern", "orthomcl")
    graph.record_type = "group"
    add_step_to_graph(
        graph,
        StrategyStep(
            id=_STEP,
            kind=StepKind.SEARCH,
            search_name=PHYLETIC_EXPRESSION_SEARCH,
            parameters={PHYLETIC_EXPRESSION_PARAM: StringValue(value=bound)},
            record_class="group",
            display_name="Phyletic Pattern",
        ),
    )
    details = WDKStrategyDetails.model_validate(
        {
            "strategyId": _STRATEGY,
            "name": "Phyletic Pattern",
            "rootStepId": _WDK_STEP,
            "stepTree": {"stepId": _WDK_STEP},
            "steps": {
                str(_WDK_STEP): {
                    "id": _WDK_STEP,
                    "searchName": PHYLETIC_EXPRESSION_SEARCH,
                    "searchConfig": {"parameters": {PHYLETIC_EXPRESSION_PARAM: held}},
                    "recordClassName": "group",
                    "estimatedSize": _RESULT,
                    "validation": {"level": "RUNNABLE", "isValid": True},
                }
            },
        }
    )
    sync = WDKSyncState(wdk_step_ids={_STEP: _WDK_STEP}, wdk_strategy_id=_STRATEGY)
    return await _bound_values(_judged("orthomcl", graph, sync, details))


@pytest.mark.parametrize("recorded", [_MORE, _MISSING], ids=["more", "missing"])
async def test_the_site_spelling_with_parentheses_passes_the_check(
    recorded: dict[str, str],
) -> None:
    check = await _check(recorded["bound"], recorded["site"])

    assert (check.kind, check.status, check.evidence) == (
        "bound_values",
        "pass",
        "the site holds every value the spec binds on 1 search step",
    )


async def test_a_changed_count_fails_the_check() -> None:
    bound = "pfal=0 AND tgon>=1 OR pfal=1 AND tgon>=3"
    held = "(pfal=0 AND tgon>=1) OR (pfal=1 AND tgon>=2)"

    named = f"step {_WDK_STEP} ('Phyletic Pattern')"

    check = await _check(bound, held)

    assert (check.status, check.evidence) == (
        "fail",
        f"{named} holds {held!r} for {PHYLETIC_EXPRESSION_PARAM}, the spec binds {bound!r}",
    )
