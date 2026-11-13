from __future__ import annotations

from veupathdb.domain.parameters import StringValue

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead.frame_requirements import requirements_no_search_states
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    FoldChangeValue,
)
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
)
from strategist.tests._support.bound_values import bound
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_FOLD = Constraint(
    kind=ConstraintKind.FOLD_CHANGE,
    requested_value="2-fold",
    label="2-fold",
    source=ConstraintSource.USER_EXPLICIT,
    value=FoldChangeValue(cut=2),
)


def _no_search_states(*answers: RequirementLink) -> list[Constraint]:
    signal = Criterion(
        id="c_signal",
        text="with a signal peptide",
        search_name="GenesWithSignalPeptide",
        resolved_params=bound({"fold_change": StringValue(value="2")}),
        answers=list(answers),
    )
    domain = StrategyDomainState(
        requirements=[_FOLD],
        operational_spec=OperationalSpec(goal="g", criteria=[signal]),
    )
    return requirements_no_search_states(lead_deps(pipeline_state(domain=domain)), [])


def test_a_fold_change_no_criterion_links_is_offered_for_withdrawal() -> None:
    assert _no_search_states() == [_FOLD]


def test_a_fold_change_a_criterion_links_is_not_offered() -> None:
    assert (
        _no_search_states(RequirementLink(requirement=_FOLD.id, param="fold_change"))
        == []
    )
