"""The classifier records a combination only under the researcher's own operator."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.agents.verification import _VERIFICATION_INSTRUCTIONS
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
    is_blocking,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.domain.strategy._vaccine_request import (
    VACCINE,
    VACCINE_TERMS,
)

_CRITERIA = [
    Criterion(
        id="c_stage",
        text="expressed in late schizonts or merozoites",
        search_name="GenesByRNASeqEvidence",
    ),
    Criterion(
        id="c_surface",
        text="signal peptide or GPI anchor",
        search_name="GenesBySignalPeptide",
    ),
    Criterion(
        id="c_tm",
        text="no transmembrane domains beyond a signal anchor",
        search_name="GenesByTransmembraneDomains",
    ),
    Criterion(
        id="c_proteomics",
        text="evidence of expression in proteomics data",
        search_name="GenesByMassSpec",
    ),
]


def _intent(operator: str) -> UserIntent:
    return UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="blood-stage vaccine candidates",
        explicit_constraints=[
            Constraint(
                kind=ConstraintKind.COMBINATION,
                requested_value=f" {operator} ".join(VACCINE_TERMS),
                label="how the requirements combine",
                source=ConstraintSource.USER_EXPLICIT,
            )
        ],
    )


def _chain(operator: CombineOp) -> SpecStructure:
    node = StructureNode(kind="leaf", criterion_id=_CRITERIA[0].id)
    for criterion in _CRITERIA[1:]:
        node = StructureNode(
            kind="combine",
            operator=operator,
            inputs=[node, StructureNode(kind="leaf", criterion_id=criterion.id)],
        )
    return SpecStructure(root=node)


def _combination_after_build(operator: CombineOp) -> GroundedConstraint:
    state = pipeline_state(user_prompt=VACCINE)
    intent = _intent("AND")
    classify_user_intent(
        run_context_for(lead_deps(state), tool_call_id="call_classify"), intent
    )
    state.domain.operational_spec = OperationalSpec(
        goal="vaccine candidates", criteria=_CRITERIA, structure=_chain(operator)
    )
    [grounded] = [
        g
        for g in derive_ledger(state, intent).constraints.grounded
        if g.constraint.kind is ConstraintKind.COMBINATION
    ]
    return grounded


def test_a_hoisted_or_is_refused_and_names_the_connectives() -> None:
    state = pipeline_state(user_prompt=VACCINE)
    ctx = run_context_for(lead_deps(state), tool_call_id="call_classify")

    with pytest.raises(ModelRetry) as refused:
        classify_user_intent(ctx, _intent("OR"))

    text = str(refused.value)
    assert '", and "' in text
    assert '"no transmembrane domains beyond a signal anchor"' in text
    assert "split the request into separate constraints" in text
    assert "alternative within it, not a top-level OR" in text
    assert state.domain.requirements == []
    assert ctx.deps.intent is None


def test_the_same_requirements_joined_by_and_are_recorded_as_the_users() -> None:
    state = pipeline_state(user_prompt=VACCINE)

    classify_user_intent(
        run_context_for(lead_deps(state), tool_call_id="call_classify"),
        _intent("AND"),
    )

    assert [(c.source, c.hard) for c in state.domain.requirements] == [
        (ConstraintSource.USER_EXPLICIT, True),
    ]


def test_an_intersect_build_honors_the_stated_and() -> None:
    grounded = _combination_after_build(CombineOp.INTERSECT)

    assert grounded.status is ConstraintStatus.GROUNDED
    assert grounded.realized_value == "INTERSECT"
    assert is_blocking(grounded) is False


def test_a_union_build_breaks_the_stated_and() -> None:
    grounded = _combination_after_build(CombineOp.UNION)

    assert grounded.status is ConstraintStatus.UNGROUNDABLE
    assert is_blocking(grounded) is True


def test_the_classifier_is_told_never_to_hoist_an_inner_or() -> None:
    guidance = " ".join((classify_user_intent.__doc__ or "").split())

    assert "the researcher's own connective between the requirements" in guidance
    assert 'An "or" inside one requirement stays inside it' in guidance
    assert 'joined by commas and "and" is AND' in guidance
    assert "Never hoist" in guidance


def test_verify_reads_a_combination_by_its_operator_and_its_arithmetic() -> None:
    guidance = " ".join(_VERIFICATION_INSTRUCTIONS.split())

    assert "matches the researcher's connective" in guidance
    assert "never an intersection of requirements" in guidance


def test_verify_reads_the_intent_as_the_request_and_the_users_constraints() -> None:
    guidance = " ".join(_VERIFICATION_INSTRUCTIONS.split())

    assert (
        "The intent you verify is every message the researcher wrote for this "
        "request, pinned under its own heading, plus the user-explicit constraints "
        "in the ledger."
    ) in guidance
    assert "where it and the request differ, the request decides" in guidance
    assert "A criterion the spec dropped is not part of the intent" in guidance
    assert "A request that names no organism cannot fail on species" in guidance


def test_a_second_classification_that_changes_nothing_is_refused() -> None:
    state = pipeline_state(user_prompt=VACCINE)
    ctx = run_context_for(lead_deps(state), tool_call_id="call_classify")
    classify_user_intent(ctx, _intent("AND"))

    with pytest.raises(ModelRetry) as refused:
        classify_user_intent(ctx, _intent("AND"))

    assert "already classified as new_strategy" in str(refused.value)
    assert len(state.domain.requirements) == 1


def test_a_second_classification_may_change_the_classification() -> None:
    state = pipeline_state(user_prompt=VACCINE)
    ctx = run_context_for(lead_deps(state), tool_call_id="call_classify")
    classify_user_intent(ctx, _intent("AND"))
    changed = _intent("AND").model_copy(
        update={"classification": IntentClassification.EXTEND_STRATEGY}
    )

    classify_user_intent(ctx, changed)

    assert ctx.deps.intent is changed
