"""A value Strategist cannot read goes back to WDK exactly as WDK holds it."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, override

import pytest
from veupathdb.domain.parameters import (
    HeldValue,
    NumberValue,
    ParamSpecNormalized,
    ParamValue,
    StringValue,
    fill_site_set_defaults,
    wire_map,
)
from veupathdb.domain.strategy import (
    StepKind,
    StepSettings,
    StepValidation,
    StrategyAst,
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.wdk import NewStepSpec, StrategyAPI, WDKIdentifier, WDKSearchConfig
from veupathdb_mcp.catalog import ValidatedParams
from veupathdb_mcp.wdk import WireStep

from strategist.ai.agents.strategy_instructions import _render_step_params
from strategist.domain.strategy.operations import (
    AddLeafOp,
    AttachNewRoot,
    UpdateStepParamsOp,
)
from strategist.domain.strategy.operations.apply import apply_operation
from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.strategy.spec_hydration import spec_from_ast
from strategist.domain.strategy.spec_tree import node_for
from strategist.persistence.models import PersistedStrategyGraph
from strategist.services.conversations.responses import derive_steps_from_strategy_ast
from strategist.services.experiment import variant_comparison
from strategist.services.experiment.variant_comparison import (
    VariantComparison,
    VariantResult,
    VariantSpec,
    counted_in_place,
)
from strategist.services.separation.thread_searches import thread_searches
from strategist.services.strategies import site_changes, stated_sides
from strategist.services.strategies._wdk_step_calls import _put_search_config
from strategist.services.strategies.session_factory import build_strategy_session
from strategist.services.strategies.stated_sides import canonical_batch
from strategist.services.strategies.sync_state import WDKSyncState, ensure_sync_state
from strategist.tests._support.recording_wdk import RecordingWDK
from strategist.tests._support.wdk_write_stubs import commit_against

_RETIRED: dict[str, ParamValue] = {
    "text_expression": HeldValue(wire="kinase"),
    "text_fields": HeldValue(wire="product, notes"),
}
_REFUSED = StepValidation.model_validate(
    {"level": "RUNNABLE", "isValid": False, "errors": {"general": ["Retired"]}}
)
_SIBLING: dict[str, ParamValue] = {
    "max_weight": NumberValue(value=50),
    "min_weight": HeldValue(wire="abc"),
}


def _imported() -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="10", search_name="GenesByRetiredText", parameters=dict(_RETIRED)
        ),
        wdk_step_ids={"10": 10},
        step_validations={"10": _REFUSED},
    )


def _weight_graph(parameters: dict[str, ParamValue]) -> StrategyGraph:
    graph = StrategyGraph("g", "g", "plasmodb")
    graph.steps["10"] = StrategyStep(
        id="10",
        kind=StepKind.SEARCH,
        search_name="GenesByMolecularWeight",
        parameters=dict(parameters),
    )
    graph.recompute_roots()
    return graph


async def _put(monkeypatch: pytest.MonkeyPatch, step: StrategyStep) -> dict[str, str]:
    sent: list[WDKSearchConfig] = []

    async def record(**kwargs: Any) -> None:
        sent.append(kwargs["search_config"])

    api = StrategyAPI.__new__(StrategyAPI)
    monkeypatch.setattr(api, "update_step_search_config", record)
    await _put_search_config(
        api,
        WDKSyncState(wdk_step_ids={step.id: 10}),
        step,
        "transcript",
        StepSettings(),
    )
    return dict(sent[0].parameters)


def test_an_imported_retired_step_keeps_its_values_and_wdks_verdict() -> None:
    session = build_strategy_session(
        site_id="plasmodb",
        strategy_graph=PersistedStrategyGraph(id="t", strategy_ast=_imported()),
    )
    graph = session.graph
    assert graph is not None
    response = derive_steps_from_strategy_ast(_imported())[0]

    assert graph.steps["10"].parameters == _RETIRED
    assert ensure_sync_state(session).step_validations == {"10": _REFUSED}
    assert (response.parameters, response.validation) == (_RETIRED, _REFUSED)


async def test_an_imported_retired_step_is_created_byte_identical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[WDKSearchConfig] = []

    class _Api(RecordingWDK):
        @override
        async def create_step(
            self, spec: NewStepSpec, record_type: str, user_id: str | None = None
        ) -> WDKIdentifier:
            created.append(spec.search_config)
            return await super().create_step(spec, record_type, user_id)

    step = StrategyStepNode(
        id="10", search_name="GenesByRetiredText", parameters=dict(_RETIRED)
    )

    await commit_against(monkeypatch, _Api(), step, before=None, held={})

    assert dict(created[0].parameters) == {
        "text_expression": "kinase",
        "text_fields": "product, notes",
    }


async def test_an_edit_to_a_sibling_sends_the_held_value_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _weight_graph(_SIBLING)

    apply_operation(
        graph,
        UpdateStepParamsOp(
            step_id="10", parameters={"max_weight": NumberValue(value=60)}
        ),
    )

    assert await _put(monkeypatch, graph.steps["10"]) == {
        "max_weight": "60",
        "min_weight": "abc",
    }


def test_stating_the_held_parameter_replaces_it() -> None:
    graph = _weight_graph(_SIBLING)

    apply_operation(
        graph,
        UpdateStepParamsOp(
            step_id="10", parameters={"min_weight": StringValue(value="7")}
        ),
    )

    assert graph.steps["10"].parameters["min_weight"] == StringValue(value="7")


def test_the_agent_reads_a_held_value_as_kept_as_the_site_holds_it() -> None:
    step = _weight_graph(_SIBLING).steps["10"]

    assert "min_weight='abc' (kept as the site holds it)" in _render_step_params(
        step, None
    )


def test_a_rebuild_from_the_spec_keeps_the_held_value() -> None:
    spec = spec_from_ast(_imported(), goal="g", listed={})
    [criterion] = spec.criteria

    assert criterion.step_parameters == _RETIRED
    assert node_for(criterion).parameters == _RETIRED


def test_a_rebuild_through_an_operation_keeps_the_held_value() -> None:
    graph = StrategyGraph("g", "g", "plasmodb")

    apply_operation(
        graph,
        AddLeafOp(
            step=StrategyStepNode(
                id="10", search_name="GenesByRetiredText", parameters=dict(_RETIRED)
            ),
            attach=AttachNewRoot(),
        ),
    )

    assert graph.steps["10"].parameters == _RETIRED


async def test_validation_never_fills_a_default_over_a_held_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hidden = ParamSpecNormalized(
        name="min_weight",
        param_type="number",
        is_visible=False,
        initial_display_value="0",
    )

    async def _validate(*_args: Any, **kwargs: Any) -> ValidatedParams:
        canonical = dict(kwargs["stated"])
        held = {n: v for n, v in kwargs["context"].items() if n not in canonical}
        filled = fill_site_set_defaults({"min_weight": hidden}, {**held, **canonical})
        return ValidatedParams(
            params={n: v for n, v in filled.items() if n not in held},
            record_class="transcript",
        )

    async def _listed(_site: str, names: list[str]) -> dict[str, str]:
        return dict.fromkeys(names, "transcript")

    monkeypatch.setattr(stated_sides, "validate_parameters", _validate)
    monkeypatch.setattr(stated_sides, "search_record_types", _listed)
    graph = _weight_graph(_SIBLING)
    edit = UpdateStepParamsOp(
        step_id="10", parameters={"max_weight": NumberValue(value=60)}
    )

    batch = await canonical_batch(
        graph=graph, stated={}, site_id="plasmodb", ops=[edit]
    )
    [op] = batch.ops
    apply_operation(graph, op)

    assert graph.steps["10"].parameters == {
        "max_weight": NumberValue(value=60),
        "min_weight": HeldValue(wire="abc"),
    }


async def _site_read(
    monkeypatch: pytest.MonkeyPatch, held: ParamValue, site: str
) -> StrategyStep:
    monkeypatch.setattr(
        site_changes, "get_strategy_api", lambda _site: SimpleNamespace(client=None)
    )
    step = _weight_graph({"min_weight": held}).steps["10"]
    wire = WireStep(record_class=None, parameters={"min_weight": site})

    await site_changes._take_the_parameters(
        step, "GenesByMolecularWeight", wire, site_id="plasmodb"
    )
    return step


async def test_a_site_change_to_a_held_value_is_taken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = await _site_read(monkeypatch, HeldValue(wire="abc"), "7")

    assert step.parameters == {"min_weight": HeldValue(wire="7")}


async def test_a_held_and_a_typed_value_are_compared_on_the_wire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    same = await _site_read(monkeypatch, NumberValue(value=7), "7")
    moved = await _site_read(monkeypatch, NumberValue(value=7), "abc")

    assert same.parameters == {"min_weight": NumberValue(value=7)}
    assert moved.parameters == {"min_weight": HeldValue(wire="abc")}


async def test_a_variant_that_states_the_held_parameter_is_counted_at_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counted: list[dict[str, str]] = []

    async def _counts(ast: StrategyAst, site_id: str) -> dict[str, int]:
        del site_id
        counted.append(wire_map(ast.root.parameters))
        return {ast.root.id: 3}

    monkeypatch.setattr(variant_comparison, "compute_plan_step_counts", _counts)
    strategy = StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="10", search_name="GenesByMolecularWeight", parameters=dict(_SIBLING)
        ),
    )
    spec = VariantSpec(
        label="a",
        search_name="GenesByMolecularWeight",
        parameters={"min_weight": NumberValue(value=7)},
        record_type="transcript",
    )
    comparison = VariantComparison(
        variants=[
            VariantResult(
                label="a",
                search_name="GenesByMolecularWeight",
                gene_count=3,
                unique_count=0,
                sample_unique_genes=[],
            )
        ],
        overlaps=[],
    )

    await counted_in_place(
        "plasmodb", comparison, [spec], strategy=strategy, steps={"a": "10"}
    )

    assert counted == [{"max_weight": "50", "min_weight": "7"}]


def test_a_thread_search_carries_the_held_value() -> None:
    graph = StrategyGraph("g", "g", "plasmodb")
    graph.steps = flatten_tree(
        StrategyStepNode(search_name="GenesByRetiredText", parameters=dict(_RETIRED))
    )

    [search] = thread_searches(graph)

    assert search.parameters == _RETIRED
