from __future__ import annotations

import pytest
from veupathdb.domain.parameters import FilterValue, MultiPickValue, ParamValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree
from veupathdb.wdk import StrategyAPI, WDKStep
from veupathdb_mcp.wdk import WireStep

from strategist.domain.strategy.session import StrategyGraph
from strategist.services.strategies import site_changes

_STEP = "step_snps"
_ORGANISM = "organismSinglePick"
_SAMPLES = "variation_sample_meta"
_PF = "Plasmodium falciparum 3D7"
_VIVAX = "Plasmodium vivax P01"


async def _no_site_read(
    payload: StrategyAst, api: StrategyAPI, wire: dict[str, WireStep]
) -> None:
    del payload, api, wire
    msg = "an equal value needs no site read"
    raise AssertionError(msg)


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(site_changes, "canonicalize_synced_parameters", _no_site_read)
    monkeypatch.setattr(site_changes, "get_strategy_api", lambda _site: None)


def _bound(params: dict[str, ParamValue]) -> StrategyGraph:
    graph = StrategyGraph("g1", "snps", "plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(id=_STEP, search_name="GenesByNgsSnps", parameters=params)
    )
    graph.recompute_roots()
    return graph


def _site(params: dict[str, str]) -> WDKStep:
    return WDKStep.model_validate(
        {
            "id": 440537303,
            "searchName": "GenesByNgsSnps",
            "recordClassName": "transcript",
            "searchConfig": {"parameters": params},
        }
    )


@pytest.mark.parametrize(
    ("bound", "held"),
    [
        (
            {_ORGANISM: MultiPickValue(values=[_PF, _VIVAX])},
            {_ORGANISM: f'["{_VIVAX}","{_PF}"]'},
        ),
        ({_SAMPLES: FilterValue()}, {_SAMPLES: '{"filters": []}'}),
    ],
    ids=["reordered-multi-pick", "spaced-no-filter"],
)
async def test_the_same_value_in_another_writing_is_no_outside_change(
    bound: dict[str, ParamValue], held: dict[str, str]
) -> None:
    moved = await site_changes.values_the_site_holds_otherwise(
        _bound(bound).steps[_STEP], _site(held), "plasmodb"
    )

    assert moved == {}
