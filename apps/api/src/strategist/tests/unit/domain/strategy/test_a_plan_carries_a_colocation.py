from __future__ import annotations

import pytest
from pydantic import ValidationError
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    ColocationParams,
    CombineOp,
    StrategyAst,
    StrategyStepNode,
)

from strategist.ai.agents.state import AgentToolState
from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead.pre_turn import refresh_live_strategy_state
from strategist.ai.tools.standalone.frame_structure import set_structure
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.operator_reading import with_operator
from strategist.domain.strategy.session import StrategySession
from strategist.domain.strategy.spec_hydration import spec_from_ast
from strategist.domain.strategy.spec_tree import build_step_tree
from strategist.domain.strategy.stated_regions import spec_with_the_regions_it_runs
from strategist.tests._support.organism_reads import serve_organism_reads
from strategist.tests._support.record_classes import list_every_search_under
from strategist.tests._support.recorded_searches import suite_search
from strategist.tests.unit.ai.lead.conftest import lead_runtime, pipeline_state
from strategist.tests.unit.ai.tools.conftest import agent_run_context
from strategist.tests.unit.domain.strategy._builders import (
    applied,
    graph_of,
    plan,
    spec_of,
)

_SPAN = "search_genes_by_span_logic"
_CONTAINS = ColocationParams(operation="contains", strand="same strand")


def _site_defaults() -> ColocationParams:
    held = {
        p.name: str(p.initial_display_value)
        for p in suite_search(_SPAN).parameters or []
        if p.initial_display_value is not None
    }
    return ColocationParams.from_wdk_params({**held, "span_output": "a"})


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _criteria() -> list[Criterion]:
    return [
        Criterion(id="c_kin", text="kinases", search_name="GenesByText"),
        Criterion(id="c_snp", text="snps", search_name="GenesByGoTerm"),
    ]


def _spec(root: StructureNode) -> OperationalSpec:
    return OperationalSpec(
        goal="kinases near snps",
        criteria=_criteria(),
        structure=SpecStructure(root=root),
    )


def _union() -> StructureNode:
    return StructureNode(
        kind="combine",
        operator=CombineOp.UNION,
        inputs=[_leaf("c_kin"), _leaf("c_snp")],
    )


def _colocated(params: ColocationParams) -> StructureNode:
    return StructureNode(
        kind="combine",
        operator=CombineOp.COLOCATE,
        colocation_params=params,
        inputs=[_leaf("c_kin"), _leaf("c_snp")],
    )


def test_an_unstated_colocation_field_takes_the_sites_default() -> None:
    assert _site_defaults() == ColocationParams()


def test_a_colocated_pick_builds_on_the_sites_defaults() -> None:
    picked = with_operator(_spec(_union()), ["c_kin", "c_snp"], CombineOp.COLOCATE)

    root = build_step_tree(picked)

    assert (root.operator, root.colocation_params) == (
        CombineOp.COLOCATE,
        _site_defaults(),
    )


def test_a_colocated_pick_keeps_the_parameters_it_was_given() -> None:
    picked = with_operator(
        _spec(_union()), ["c_kin", "c_snp"], CombineOp.COLOCATE, _CONTAINS
    )

    assert build_step_tree(picked).colocation_params == _CONTAINS


def test_a_pick_away_from_colocated_drops_the_parameters() -> None:
    picked = with_operator(
        _spec(_colocated(_CONTAINS)), ["c_kin", "c_snp"], CombineOp.UNION
    )

    assert picked.structure == SpecStructure(root=_union())


def test_a_union_carrying_colocation_parameters_is_refused() -> None:
    with pytest.raises(ValidationError):
        StructureNode(
            kind="combine",
            operator=CombineOp.UNION,
            colocation_params=ColocationParams(),
            inputs=[_leaf("c_kin"), _leaf("c_snp")],
        )


def test_a_colocation_without_parameters_builds_on_the_sites_defaults() -> None:
    node = StructureNode(
        kind="combine",
        operator=CombineOp.COLOCATE,
        inputs=[_leaf("c_kin"), _leaf("c_snp")],
    )

    assert (node.colocation_params, build_step_tree(_spec(node)).colocation_params) == (
        None,
        _site_defaults(),
    )


async def test_a_frame_structure_states_the_colocation_it_builds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_organism_reads(monkeypatch, ["Plasmodium falciparum 3D7"])
    list_every_search_under(monkeypatch, "transcript")
    state = AgentToolState()
    for criterion in _criteria():
        state.frame_set_criterion(criterion)
    root = StructureNode.model_validate(
        {
            "kind": "combine",
            "operator": "COLOCATE",
            "colocationParams": {"operation": "contains", "strand": "same strand"},
            "inputs": [
                {"kind": "leaf", "criterionId": "c_kin"},
                {"kind": "leaf", "criterionId": "c_snp"},
            ],
        }
    )

    await set_structure(agent_run_context(agent_state=state), root=root)

    built = build_step_tree(state.operational_spec_draft)
    assert (built.operator, built.colocation_params) == (CombineOp.COLOCATE, _CONTAINS)
    assert built.colocation_params == _site_defaults().model_copy(
        update={"operation": "contains", "strand": "same strand"}
    )


def _two_leaves(
    operator: CombineOp, params: ColocationParams | None
) -> StrategyStepNode:
    return StrategyStepNode(
        id="step_join",
        search_name=COMBINE_SEARCH_NAME,
        operator=operator,
        colocation_params=params,
        primary_input=StrategyStepNode(id="step_kin", search_name="GenesByText"),
        secondary_input=StrategyStepNode(id="step_snp", search_name="GenesByGoTerm"),
    )


def test_a_colocation_reads_back_into_the_plan() -> None:
    spec = spec_from_ast(
        StrategyAst(
            record_type="transcript",
            root=_two_leaves(CombineOp.COLOCATE, _CONTAINS),
        ),
        goal="g",
        listed={},
    )

    assert spec.structure is not None
    assert spec.structure.root.colocation_params == _CONTAINS


def test_an_edit_from_a_union_to_a_colocation_is_applied() -> None:
    held = _two_leaves(CombineOp.UNION, None)
    before = spec_of(held)
    assert before.structure is not None
    after = before.model_copy(
        update={
            "structure": SpecStructure(
                root=StructureNode(
                    kind="combine",
                    operator=CombineOp.COLOCATE,
                    colocation_params=_CONTAINS,
                    inputs=before.structure.root.inputs,
                )
            )
        }
    )

    graph = applied(held, plan(before, after, graph_of(held)))

    ast = graph.to_strategy_ast()
    assert ast is not None
    assert (ast.root.operator, ast.root.colocation_params) == (
        CombineOp.COLOCATE,
        _CONTAINS,
    )


_UPSTREAM = ColocationParams(
    region_a="custom", begin_direction_a="-", begin_offset_a=1000
)


def _stored_without_a_region(spec: OperationalSpec) -> OperationalSpec:
    dumped = spec.model_dump(by_alias=True, mode="json")
    del dumped["structure"]["root"]["colocationParams"]
    return OperationalSpec.model_validate(dumped)


def test_a_text_edit_over_a_stored_region_writes_nothing_to_the_join() -> None:
    held = _two_leaves(CombineOp.COLOCATE, _UPSTREAM)
    before = _stored_without_a_region(spec_of(held))
    after = before.model_copy(
        update={
            "criteria": [
                c.model_copy(update={"text": f"{c.text}, restated"})
                for c in before.criteria
            ]
        }
    )

    ops = plan(before, after, graph_of(held))

    assert (ops, applied(held, ops).steps["step_join"].colocation_params) == (
        [],
        _UPSTREAM,
    )


def test_a_stored_region_is_read_back_from_the_join_the_graph_holds() -> None:
    held = _two_leaves(CombineOp.COLOCATE, _UPSTREAM)

    spec = spec_with_the_regions_it_runs(
        _stored_without_a_region(spec_of(held)), graph_of(held)
    )

    assert spec.structure is not None
    assert spec.structure.root.colocation_params == _UPSTREAM


def test_a_stored_region_with_no_join_takes_the_sites_defaults() -> None:
    held = _two_leaves(CombineOp.COLOCATE, _UPSTREAM)
    stored = _stored_without_a_region(spec_of(held))

    spec = spec_with_the_regions_it_runs(
        stored, graph_of(_two_leaves(CombineOp.UNION, None))
    )

    assert spec.structure is not None
    assert spec.structure.root.colocation_params == _site_defaults()


async def test_a_turn_opens_on_the_region_its_join_runs() -> None:
    held = _two_leaves(CombineOp.COLOCATE, _UPSTREAM)
    session = StrategySession(site_id="plasmodb")
    session.graph = graph_of(held)
    stored = _stored_without_a_region(spec_of(held))
    state = pipeline_state(
        domain=StrategyDomainState(operational_spec=stored, answered_spec=stored)
    )

    refreshed = await refresh_live_strategy_state(
        state, lead_runtime(strategy_session=session)
    )

    assert [
        spec.structure.root.colocation_params
        for spec in (refreshed.domain.operational_spec, refreshed.domain.answered_spec)
        if spec is not None and spec.structure is not None
    ] == [_UPSTREAM, _UPSTREAM]
