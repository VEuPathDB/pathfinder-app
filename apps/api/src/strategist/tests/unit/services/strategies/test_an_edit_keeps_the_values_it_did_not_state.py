from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.domain.strategy import StrategyStepNode

from strategist.domain.strategy.operations import ReplaceStrategyOp, UpdateStepParamsOp
from strategist.services.strategies import commit_tree, stated_sides
from strategist.services.strategies.commit import apply_operations_and_commit
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.spec_build import build_strategy_from_spec
from strategist.tests._support.wdk_write_stubs import accepts_every_value
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    Env,
    new_thread,
)

_KEPT: dict[str, ParamValue] = {
    "domain_database": SinglePickValue(value="Pfam"),
    "domain_accession": StringValue(value="N/A"),
    "domain_typeahead": MultiPickValue(values=["PF00069"]),
}


def _domain(organism: str) -> StrategyStepNode:
    return StrategyStepNode(
        id="c_domain",
        search_name="GenesByInterproDomain",
        display_name="Protein kinase domain",
        parameters={"organism": MultiPickValue(values=[organism]), **_KEPT},
    )


_SENT = {
    "domain_database": "Pfam",
    "domain_accession": "N/A",
    "domain_typeahead": '["PF00069"]',
}


def _kept_on_the_wire(body: Any) -> dict[str, str]:
    return {name: body["parameters"][name] for name in _SENT}


def _thread(monkeypatch: pytest.MonkeyPatch) -> tuple[Env, StrategyMutationContext]:
    env = Env(monkeypatch)
    for module in (stated_sides, commit_tree):
        monkeypatch.setattr(module, "validate_parameters", accepts_every_value)
    return env, new_thread()


def _as_typed(values: dict[str, ParamValue]) -> dict[str, object]:
    return {name: value.model_dump(mode="json") for name, value in values.items()}


def _stored(deps: StrategyMutationContext) -> dict[str, object]:
    graph = deps.strategy_session.graph
    assert graph is not None
    return _as_typed(dict(graph.steps["c_domain"].parameters))


async def test_an_organism_edit_keeps_the_other_values_as_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env, deps = _thread(monkeypatch)
    await apply_operations_and_commit(
        deps=deps,
        ops=[ReplaceStrategyOp(root=_domain("Toxoplasma gondii ME49"), name="Kinases")],
    )
    env.wdk.writes.clear()

    await apply_operations_and_commit(
        deps=deps,
        ops=[
            UpdateStepParamsOp(
                step_id="c_domain",
                parameters={
                    "organism": MultiPickValue(values=["Toxoplasma gondii GT1"])
                },
            )
        ],
    )

    [put] = env.wdk.written("PUT", "/search-config")
    assert _kept_on_the_wire(put.body) == _SENT
    assert _stored(deps) == _as_typed(
        {"organism": MultiPickValue(values=["Toxoplasma gondii GT1"]), **_KEPT}
    )


async def test_a_rebuild_that_moves_the_organism_keeps_the_other_values_as_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env, deps = _thread(monkeypatch)
    await build_strategy_from_spec(deps=deps, root=_domain("Toxoplasma gondii ME49"))
    env.wdk.writes.clear()

    await build_strategy_from_spec(deps=deps, root=_domain("Toxoplasma gondii GT1"))

    [put] = env.wdk.written("PUT", "/search-config")
    assert _kept_on_the_wire(put.body) == _SENT
    assert _stored(deps) == _as_typed(
        {"organism": MultiPickValue(values=["Toxoplasma gondii GT1"]), **_KEPT}
    )
