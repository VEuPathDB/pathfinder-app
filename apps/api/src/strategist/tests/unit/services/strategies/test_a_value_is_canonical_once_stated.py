"""A value is canonical when it is stated, and every push sends the map as it is."""

from __future__ import annotations

import json
from typing import Any, override

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
from veupathdb.wdk import (
    NewStepSpec,
    WDKIdentifier,
    WDKSearchConfig,
    WDKSearchResponse,
    WDKStep,
)
from veupathdb_mcp.catalog import ValidatedParams

from strategist.domain.strategy.operations import UpdateStepParamsOp
from strategist.domain.strategy.operations.apply import apply_operation
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.services.strategies import (
    commit_tree,
    stated_sides,
)
from strategist.services.strategies.commit_tree import CommittedTree
from strategist.services.strategies.save_substrategy import save_subtree_as_strategy
from strategist.services.strategies.stated_sides import canonical_batch
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.record_classes import list_every_search_under
from strategist.tests._support.recording_wdk import RecordingWDK

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


class _Api(RecordingWDK):
    def __init__(self, refusals: int = 0) -> None:
        super().__init__()
        self._refusals = refusals

    @property
    def created(self) -> list[dict[str, str]]:
        return [call.kwargs["parameters"] for call in self.named("create_step")]

    @property
    def written(self) -> list[dict[str, str]]:
        return [
            call.kwargs["parameters"]
            for call in self.named("update_step_search_config")
        ]

    def _refused(self) -> None:
        if self._refusals:
            self._refusals -= 1
            msg = "WDK refused the step"
            raise WDKError(msg, 502)

    @override
    async def create_step(
        self, spec: NewStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        made = await super().create_step(spec, record_type, user_id)
        self._refused()
        return made

    @override
    async def update_step_search_config(
        self,
        step_id: int,
        search_config: WDKSearchConfig,
        record_type: str,
        search_name: str,
        *,
        user_id: str | None = None,
        held: WDKStep | None = None,
    ) -> None:
        await super().update_step_search_config(
            step_id, search_config, record_type, search_name, user_id=user_id, held=held
        )
        self._refused()


def _serve(monkeypatch: pytest.MonkeyPatch, api: _Api) -> None:
    monkeypatch.setattr(commit_tree, "validate_parameters", _validate)
    monkeypatch.setattr(commit_tree, "get_strategy_api", lambda _site: api)
    list_every_search_under(monkeypatch, "transcript")


async def _commit(
    graph: StrategyGraph, before: StrategyAst | None, sync_state: WDKSyncState
) -> CommittedTree:
    return await commit_tree.commit_tree(
        site_id="plasmodb",
        steps=graph.steps,
        root_id="s",
        old=before,
        sync_state=sync_state,
        target=commit_tree.CommitTarget(name="g", description=""),
    )


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

    sync_state = WDKSyncState(wdk_step_ids={"s": 9})
    before = _ast(_BRANCH, 50)
    api.holds(flatten_tree(before.root), sync_state)

    await _commit(graph, before, sync_state)

    assert graph.steps["s"].parameters == _values(_BRANCH, 60)
    assert api.written == [_wire(_BRANCH, "60")]


async def test_a_failed_push_retried_sends_the_stated_canonical_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api(refusals=1)
    _serve(monkeypatch, api)
    graph = _graph(_LEAVES, 50)
    await _edit(monkeypatch, graph, {"organism": _BRANCH})

    first = await _commit(graph, None, WDKSyncState())
    second = await _commit(graph, None, WDKSyncState())

    assert ([f.step_id for f in first.failures], second.failures) == (["s"], [])
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
