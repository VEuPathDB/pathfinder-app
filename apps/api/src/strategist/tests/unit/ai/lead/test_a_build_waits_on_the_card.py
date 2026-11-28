"""A plan whose card still holds a question is not built until the researcher answers."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import StringValue

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead.lead_pins import pinned_operational_spec
from strategist.ai.lead.sub_agent_dispatch import build_strategy
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.domain.strategy.constraints import ConstraintKind
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.questions import OpenQuestion
from strategist.tests._support.run_context import run_context_for
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_DROP = (
    "No search on this site states 'predicted GPI anchor'. Drop it from the request?"
)


def _signal_peptide() -> OperationalSpec:
    return OperationalSpec(
        goal="Cytauxzoon felis genes with a GPI anchor or a signal peptide",
        criteria=[
            Criterion(
                id="c_signal_peptide",
                text="predicted signal peptide",
                search_name="GenesWithSignalPeptide",
                resolved_params={
                    "organism": BoundValue(
                        value=StringValue(value="Cytauxzoon felis strain Winnie"),
                        source="chosen",
                    )
                },
                result_count=288,
            )
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="c_signal_peptide")
        ),
    )


def _deps(*questions: OpenQuestion) -> LeadDeps:
    state = pipeline_state(
        "piroplasmadb",
        domain=StrategyDomainState(
            operational_spec=_signal_peptide(), open_questions=list(questions)
        ),
    )
    return lead_deps(state)


def _drop_question() -> OpenQuestion:
    return OpenQuestion(question=_DROP, dimension=ConstraintKind.PROPERTY)


def test_a_plan_with_an_unanswered_card_is_not_ready() -> None:
    deps = _deps(_drop_question())

    spec = deps.state.domain.operational_spec
    assert spec is not None
    assert (spec.ready_to_build, deps.state.domain.ready_to_build) == (True, False)


def test_a_plan_with_no_open_question_is_ready() -> None:
    assert _deps().state.domain.ready_to_build is True


def test_the_pin_shows_the_plan_waits_on_the_card() -> None:
    pin = pinned_operational_spec(run_context_for(_deps(_drop_question())))

    assert pin is not None
    assert "- ready_to_build: False" in pin


async def test_the_build_refuses_until_the_card_is_answered() -> None:
    deps = _deps(_drop_question())

    with pytest.raises(ModelRetry, match="consult_user") as refused:
        await build_strategy(run_context_for(deps))

    assert _DROP in str(refused.value)
    assert deps.state.domain.last_build_outcome is None
