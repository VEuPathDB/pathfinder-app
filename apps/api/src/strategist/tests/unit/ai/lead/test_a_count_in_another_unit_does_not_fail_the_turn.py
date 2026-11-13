from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import ParamValue, StringValue, param_value_from_raw
from veupathdb.domain.strategy import StepKind, StrategyStep
from veupathdb.wdk import WDKStepTree, WDKStrategyDetails

from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.domain.strategy.build_outcome import BuildOutcome
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    CountValue,
)
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.bound_values import bound
from strategist.tests._support.orthomcl_record_classes import (
    recorded_orthomcl_record_types,
)
from strategist.tests.fixtures.builders import add_step_to_graph
from strategist.tests.unit.ai.lead._site_verdict import (
    VALID,
    serve_the_site,
    verify,
)
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

pytestmark = pytest.mark.usefixtures("collector")

_STEP = "c_weight"
_WDK_STEP = 227289040
_STRATEGY = 214650970
_SEARCH = "GenesByMolecularWeight"
_DIGEST: dict[str, Any] = {
    "digest": {"prose": "The strategy answers the request.", "keyFindings": ["ok"]}
}


def _details(param: str, wire: str) -> WDKStrategyDetails:
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": _STRATEGY,
            "name": "Small proteins",
            "rootStepId": _WDK_STEP,
            "stepTree": {"stepId": _WDK_STEP},
            "steps": {
                str(_WDK_STEP): {
                    "id": _WDK_STEP,
                    "searchName": _SEARCH,
                    "searchConfig": {"parameters": {param: wire}},
                    "recordClassName": "sequence",
                    "estimatedSize": 926,
                    "validation": VALID,
                }
            },
        }
    )


def _deps(param: str, value: ParamValue, op_number: float) -> LeadDeps:
    held = Constraint(
        kind=ConstraintKind.COUNT,
        requested_value="molecular weight under 30 kDa",
        label="molecular weight",
        source=ConstraintSource.USER_EXPLICIT,
        quote="molecular weight under 30 kDa",
        value=CountValue(feature="molecular weight", op="<", value=op_number),
    )
    state = pipeline_state("orthomcl", user_prompt="molecular weight under 30 kDa")
    state.domain.operational_spec = OperationalSpec(
        goal="small proteins",
        criteria=[
            Criterion(
                id=_STEP,
                text="molecular weight under 30 kDa",
                search_name=_SEARCH,
                record_class="sequence",
                role="seed",
                answers=[RequirementLink(requirement=held.id, param=param)],
                resolved_params=bound({param: value}),
            )
        ],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id=_STEP)),
    )
    state.domain.requirements = [held]
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=[_STEP], wdk_strategy_id=_STRATEGY
    )
    graph = StrategyGraph("graph-1", "Small proteins", "orthomcl")
    graph.record_type = "sequence"
    add_step_to_graph(
        graph,
        StrategyStep(
            id=_STEP,
            kind=StepKind.SEARCH,
            search_name=_SEARCH,
            parameters={param: value},
            record_class="sequence",
            display_name="Molecular Weight",
        ),
    )
    session = StrategySession(site_id="orthomcl")
    session.add_graph(graph)
    session.sync_state = WDKSyncState(
        wdk_step_ids={_STEP: _WDK_STEP},
        step_counts={_STEP: 926},
        wdk_strategy_id=_STRATEGY,
        wdk_step_tree=WDKStepTree(step_id=_WDK_STEP),
    )
    return lead_deps(state, strategy_session=session)


async def _count_check(
    monkeypatch: pytest.MonkeyPatch, param: str, value: ParamValue, number: float
) -> tuple[bool, str, str, str | None]:
    serve_the_site(
        monkeypatch, _details(param, value.to_wire()), recorded_orthomcl_record_types()
    )
    delta = await verify(monkeypatch, _deps(param, value, number), _DIGEST)
    [check] = [c for c in delta.digest.review.checks if c.kind == ConstraintKind.COUNT]
    return delta.digest.success, check.status, check.evidence, check.why_unchecked


async def test_a_parameter_a_thousand_times_the_stated_number_is_not_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = await _count_check(
        monkeypatch, "max_molecular_weight", StringValue(value="30000"), 30
    )

    assert held == (
        True,
        "unchecked",
        (
            "asked molecular weight < 30, max_molecular_weight holds 30000: each "
            "differs from the stated number by a power of ten and nothing typed "
            "states their units"
        ),
        "no_value_to_compare",
    )


async def test_a_range_end_is_not_compared_with_a_stated_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = await _count_check(
        monkeypatch,
        "weight_range",
        param_value_from_raw({"min": 1000, "max": 30000}, "number-range"),
        30,
    )

    assert held == (
        True,
        "unchecked",
        "no linked parameter or step count holds a number to compare",
        "no_value_to_compare",
    )


async def test_a_number_the_parameter_holds_otherwise_still_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = await _count_check(
        monkeypatch, "max_molecular_weight", StringValue(value="50000"), 30000
    )

    assert held == (
        False,
        "fail",
        "asked molecular weight < 30000, max_molecular_weight holds 50000",
        None,
    )
