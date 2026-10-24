from __future__ import annotations

from typing import cast

from assistant_core.graph.turn_state import PendingApproval
from langgraph.runtime import Runtime
from pydantic import TypeAdapter
from veupathdb.domain.parameters import StringValue
from veupathdb_mcp.catalog import PhyleticPattern

from pathfinder.ai.graph import nodes
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.expression_handles import (
    BuiltPattern,
    expression_handle,
)
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.question_options import SetValues, TypedOption
from pathfinder.domain.strategy.questions import OpenQuestion
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

_ADAPTER: TypeAdapter[PhyleticPattern] = TypeAdapter(PhyleticPattern)
_PATTERN = _ADAPTER.validate_python(
    {"kind": "count", "of": {"kind": "codes", "codes": ["APIC"]}, "condition": "absent"}
)
_BOUND, _OFFERED, _PROPOSED, _DROPPED = (f"APIC=0T AND tgon>={k}T" for k in range(1, 5))


def _held(expression: str) -> tuple[str, BuiltPattern]:
    return expression_handle(expression), BuiltPattern(
        expression=expression, pattern=_PATTERN, reading="absent from APIC"
    )


def _question() -> OpenQuestion:
    return OpenQuestion(
        question="Which pattern?",
        dimension=ConstraintKind.OTHER,
        options=[
            TypedOption(
                id="o_offered",
                label="The offered one",
                binding=SetValues(
                    criterion_id="c_groups",
                    params={"phyletic_expression": expression_handle(_OFFERED)},
                ),
            ),
            TypedOption(
                id="o_bound",
                label="The bound one",
                binding=SetValues(
                    criterion_id="c_groups",
                    params={"phyletic_expression": expression_handle(_BOUND)},
                ),
            ),
        ],
    )


async def test_a_turn_keeps_only_the_built_expressions_still_referenced() -> None:
    spec = OperationalSpec(
        criteria=[
            Criterion(
                id="c_groups",
                text="groups",
                search_name="GroupsByPhyleticPattern",
                resolved_params=bound(
                    {"phyletic_expression": StringValue(value=_BOUND)}
                ),
            )
        ]
    )
    state = pipeline_state(
        "orthomcl",
        domain=StrategyDomainState(
            operational_spec=spec,
            open_questions=[_question()],
            built_expressions=dict(
                _held(e) for e in (_BOUND, _OFFERED, _PROPOSED, _DROPPED)
            ),
        ),
    )
    state.pending_approval = PendingApproval(
        phase="lead",
        tool_call_id="call_propose",
        tool_name="propose_changes",
        tool_args={"params": {"phyletic_expression": expression_handle(_PROPOSED)}},
    )

    command = await nodes.finalize_turn_node(
        state, cast("Runtime[Context]", Runtime(context=None))
    )

    update = command.update
    assert isinstance(update, dict)
    domain = update["domain"]
    assert isinstance(domain, StrategyDomainState)
    assert sorted(domain.built_expressions) == sorted(
        expression_handle(e) for e in (_BOUND, _OFFERED, _PROPOSED)
    )
