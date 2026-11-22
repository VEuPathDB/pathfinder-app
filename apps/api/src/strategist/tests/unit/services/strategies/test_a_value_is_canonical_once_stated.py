"""A value is canonical when it is stated, and every push sends the map as it is."""

from __future__ import annotations

import json
from typing import Any

import pytest
from veupathdb.domain.parameters import (
    HeldValue,
    MultiPickValue,
    NumberValue,
    ParameterCanonicalizer,
    ParamSpecNormalized,
    ParamValue,
)
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree
from veupathdb.errors import WDKError
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import WDKIdentifier, WDKSearchConfig, WDKSearchResponse
from veupathdb_mcp.catalog import ValidatedParams

from strategist.domain.strategy.operations import UpdateStepParamsOp
from strategist.domain.strategy.operations.apply import apply_operation
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.services.strategies import (
    save_substrategy,
    stated_sides,
    step_wdk_push,
)
from strategist.services.strategies.save_substrategy import save_subtree_as_strategy
from strategist.services.strategies.stated_sides import canonical_batch
from strategist.services.strategies.step_push_planner import plan_step_pushes
from strategist.services.strategies.step_wdk_push import push_steps_with_plan
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.record_classes import list_every_search_under

_BRANCH = MultiPickValue(values=["Haemoproteidae"])
_LEAVES = MultiPickValue(values=["Haemoproteus tartakovskyi strain SISKIN1"])
_SEARCH = "GenesByMolecularWeight"


def _specs() -> dict[str, ParamSpecNormalized]:
    search = WDKSearchResponse.model_validate(
        load_recorded("search_genes_by_molecular_weight").json_body()
    ).search_data
    organism = next(p for p in search.parameters or [] if p.name == "organism")
    return {
        "organism": ParamSpecNormalized(
            name="organism",
            param_type="multi-pick-vocabulary",
            vocabulary=organism.vocabulary,
            count_only_leaves=True,
        ),
        "max_molecular_weight": ParamSpecNormalized(
            name="max_molecular_weight", param_type="number"
        ),
    }


async def _validate(*_args: Any, **kwargs: Any) -> ValidatedParams:
    canonical = ParameterCanonicalizer(_specs()).canonicalize(kwargs["stated"])
    return ValidatedParams(params=canonical, record_class="transcript")


async def _listed(_site: str, names: list[str]) -> dict[str, str]:
    return dict.fromkeys(names, "transcript")


def _values(organism: ParamValue, weight: float) -> dict[str, ParamValue]:
    return {
        "organism": organism,
        "max_molecular_weight": NumberValue(value=weight),
        "retired": HeldValue(wire="a, b"),
    }


def _ast(organism: ParamValue, weight: float) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="s", search_name=_SEARCH, parameters=_values(organism, weight)
        ),
    )


def _graph(organism: ParamValue, weight: float) -> StrategyGraph:
    graph = StrategyGraph("g", "g", "plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(_ast(organism, weight).root)
    graph.steps["s"].record_class = "transcript"
    graph.recompute_roots()
    return graph


async def _edit(
    monkeypatch: pytest.MonkeyPatch,
    graph: StrategyGraph,
    parameters: dict[str, ParamValue],
) -> None:
    monkeypatch.setattr(stated_sides, "validate_parameters", _validate)
    monkeypatch.setattr(stated_sides, "search_record_types", _listed)
    edit = UpdateStepParamsOp(step_id="s", parameters=parameters)
    batch = await canonical_batch(
        graph=graph, stated={}, site_id="plasmodb", ops=[edit]
    )
    for op in batch.ops:
        apply_operation(graph, op)


class _Api:
    def __init__(self, refusals: int = 0) -> None:
        self.created: list[dict[str, str]] = []
        self.written: list[dict[str, str]] = []
        self._refusals = refusals

    def _refuse(self) -> None:
        if self._refusals:
            self._refusals -= 1
            msg = "WDK refused the step"
            raise WDKError(msg, 502)

    async def create_step(
        self, spec: Any, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del record_type, user_id
        self.created.append(dict(spec.search_config.parameters))
        self._refuse()
        return WDKIdentifier(id=11)

    async def update_step_search_config(
        self,
        step_id: int,
        search_config: WDKSearchConfig,
        record_type: str,
        search_name: str,
    ) -> None:
        del step_id, record_type, search_name
        self.written.append(dict(search_config.parameters))
        self._refuse()

    async def find_step(self, step_id: int) -> Any:
        del step_id
        raise OSError

    async def create_strategy(self, **_kwargs: Any) -> WDKIdentifier:
        return WDKIdentifier(id=7)


def _serve(monkeypatch: pytest.MonkeyPatch, api: _Api) -> None:
    monkeypatch.setattr(step_wdk_push, "validate_parameters", _validate)
    monkeypatch.setattr(step_wdk_push, "get_strategy_api", lambda _site: api)
    monkeypatch.setattr(save_substrategy, "get_strategy_api", lambda _site: api)
    list_every_search_under(monkeypatch, "transcript")


def _wire(organism: MultiPickValue, weight: str) -> dict[str, str]:
    return {
        "organism": json.dumps(organism.values),
        "max_molecular_weight": weight,
        "retired": "a, b",
    }


async def test_a_stated_branch_is_canonical_in_the_map_once_stated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _graph(_LEAVES, 50)

    await _edit(monkeypatch, graph, {"organism": _BRANCH})

    assert graph.steps["s"].parameters == _values(_LEAVES, 50)


async def test_an_edit_to_another_parameter_keeps_the_branch_wdk_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _graph(_BRANCH, 50)

    await _edit(monkeypatch, graph, {"max_molecular_weight": NumberValue(value=60)})

    assert graph.steps["s"].parameters == _values(_BRANCH, 60)


async def test_a_push_sends_the_branch_wdk_holds_and_the_held_value_as_they_are(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api()
    _serve(monkeypatch, api)
    graph = _graph(_BRANCH, 60)
    plan = plan_step_pushes(
        old_ast=_ast(_BRANCH, 50), new_ast=_ast(_BRANCH, 60), existing_wdk_ids={"s": 9}
    )

    await push_steps_with_plan(
        graph, WDKSyncState(wdk_step_ids={"s": 9}), "plasmodb", plan
    )

    assert graph.steps["s"].parameters == _values(_BRANCH, 60)
    assert api.written == [_wire(_BRANCH, "60")]


async def test_a_failed_push_retried_sends_the_stated_canonical_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api(refusals=1)
    _serve(monkeypatch, api)
    graph = _graph(_LEAVES, 50)
    await _edit(monkeypatch, graph, {"organism": _BRANCH})
    plan = plan_step_pushes(
        old_ast=None, new_ast=_ast(_LEAVES, 50), existing_wdk_ids={}
    )

    first = await push_steps_with_plan(graph, WDKSyncState(), "plasmodb", plan)
    second = await push_steps_with_plan(graph, WDKSyncState(), "plasmodb", plan)

    assert (first.failed, second.failed) == (["s"], [])
    assert api.created == [_wire(_LEAVES, "50"), _wire(_LEAVES, "50")]


async def test_a_saved_subtree_sends_read_values_as_read_and_stated_ones_canonical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api()
    _serve(monkeypatch, api)
    graph = _graph(_BRANCH, 50)
    await _edit(monkeypatch, graph, {"max_molecular_weight": NumberValue(value=60)})
    session = StrategySession(site_id="plasmodb")
    session.add_graph(graph)

    await save_subtree_as_strategy(
        session=session, site_id="plasmodb", source_step_id="s", name="saved"
    )

    assert api.created == [_wire(_BRANCH, "60")]
