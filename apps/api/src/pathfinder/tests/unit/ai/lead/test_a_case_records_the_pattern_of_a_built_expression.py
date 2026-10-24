from __future__ import annotations

import json

from pydantic import TypeAdapter
from veupathdb.domain.parameters import StringValue
from veupathdb_mcp.catalog import PhyleticPattern

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.case_memory import collect_case_candidates
from pathfinder.domain.strategy.build_outcome import (
    BuildOutcome,
    BuiltCounts,
    NodeResult,
)
from pathfinder.domain.strategy.expression_handles import (
    BuiltPattern,
    expression_handle,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

_SEARCH = "GroupsByPhyleticPattern"
_BUILT = "pfal=0 AND tgon>=1 OR pfal=1 AND tgon>=2"
_TYPED = "APIC>=1T AND MAMM=0T"
_PATTERN_JSON = {
    "kind": "compare",
    "left": {"kind": "codes", "codes": ["tgon"]},
    "right": {"kind": "codes", "codes": ["pfal"]},
    "reading": "totals",
    "condition": "more_than",
    "factor": 1.0,
}
_ADAPTER: TypeAdapter[PhyleticPattern] = TypeAdapter(PhyleticPattern)


def _spec(expression: str) -> OperationalSpec:
    return OperationalSpec(
        goal="groups with more proteins in tgon than in pfal",
        criteria=[
            Criterion(
                id="c_more",
                text="more proteins in tgon than in pfal",
                search_name=_SEARCH,
                role="seed",
                resolved_params=bound(
                    {"phyletic_expression": StringValue(value=expression)}
                ),
            )
        ],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="c_more")),
    )


def _case_params(expression: str) -> tuple[dict[str, object], str]:
    spec = _spec(expression)
    state = pipeline_state(
        "orthomcl",
        domain=StrategyDomainState(
            operational_spec=spec,
            answered_spec=spec,
            last_build_outcome=BuildOutcome(
                pushed_step_ids=["c_more"],
                node_results=[
                    NodeResult(node_id="c_more", search_name=_SEARCH, status="ok")
                ],
            ),
            built_expressions={
                expression_handle(_BUILT): BuiltPattern(
                    expression=_BUILT,
                    pattern=_ADAPTER.validate_python(_PATTERN_JSON),
                    reading="more proteins in tgon than in pfal",
                )
            },
        ),
    )

    [(value, _)] = collect_case_candidates(
        state, counts=BuiltCounts(by_step={"c_more": 3896}, root_id="c_more")
    )

    rows = value.content["criteria"]
    assert isinstance(rows, list)
    [row] = rows
    assert isinstance(row, dict)
    params = row["params"]
    assert isinstance(params, dict)
    return params, json.dumps(value.content)


def test_a_case_records_the_pattern_of_a_built_expression_and_no_handle() -> None:
    params, text = _case_params(_BUILT)

    assert params == {"phyletic_expression": {"pattern": _PATTERN_JSON}}
    assert ("expr:" in text, _BUILT in text) == (False, False)


def test_a_case_records_a_typed_expression_as_written() -> None:
    params, text = _case_params(_TYPED)

    assert params == {"phyletic_expression": _TYPED}
    assert "expr:" not in text
