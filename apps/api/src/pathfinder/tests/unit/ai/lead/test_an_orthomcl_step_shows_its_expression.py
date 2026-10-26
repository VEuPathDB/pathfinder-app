"""An OrthoMCL step shows the expression it runs and the searches it was chosen
over, by name."""

from __future__ import annotations

from veupathdb.domain.parameters import PHYLETIC_EXPRESSION_PARAM, StringValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.step_rationale import ComparedSearch, SearchRationale
from pathfinder.domain.turn_facts import StepFact
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_EXPRESSION = "pfal+pviv+pber>=3T AND tgon=0T AND hsap+mmus=0T"

_RATIONALE = SearchRationale(
    search_name="GroupsByPhyleticPattern",
    basis="parameter",
    term="Expression",
    reason="The phyletic expression requires every Plasmodium genome and no host.",
    compared=[
        ComparedSearch(
            name="GroupsBySingleCopy",
            display_name="Single Copy Orthogroups",
            similarity=0.47,
        ),
        ComparedSearch(
            name="GroupsByTransform",
            display_name="Transform Proteins to Groups",
            similarity=0.32,
        ),
        ComparedSearch(name="AllGroups", display_name="All Groups", similarity=0.43),
    ],
    tool_call_id="call_1",
)


def _step() -> StepFact:
    criterion = Criterion(
        id="c_pattern",
        text="groups in every Plasmodium genome and in no host",
        search_name="GroupsByPhyleticPattern",
        search_display_name="Phyletic Pattern",
        record_class="group",
        resolved_params={
            PHYLETIC_EXPRESSION_PARAM: BoundValue(
                value=StringValue(value=_EXPRESSION), source="chosen"
            )
        },
        param_display_names={PHYLETIC_EXPRESSION_PARAM: "Expression"},
        rationale=_RATIONALE,
        result_count=797,
    )
    state = pipeline_state(
        "orthomcl",
        domain=StrategyDomainState(
            operational_spec=OperationalSpec(criteria=[criterion])
        ),
    )
    [step] = turn_facts(lead_deps(state)).steps
    return step


def test_the_reason_carries_no_search_scores() -> None:
    assert _step().reason == (
        "Expression: The phyletic expression requires every Plasmodium genome "
        "and no host."
    )


def test_the_searches_considered_are_named_in_order() -> None:
    assert _step().also_considered == [
        "Single Copy Orthogroups",
        "Transform Proteins to Groups",
        "All Groups",
    ]


def test_the_expression_row_carries_the_expression_it_runs() -> None:
    [row] = _step().parameters

    assert (row.display_name, row.expression) == ("Expression", _EXPRESSION)


def test_the_step_lines_name_the_searches_considered() -> None:
    assert (
        "Also considered: Single Copy Orthogroups, Transform Proteins to Groups, "
        "All Groups"
    ) in _step().lines()
