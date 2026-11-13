"""A held combination the message quotes is the researcher's; its check names
the operator its linked criteria meet at and is never a pass or a fail, because
no word of it is read as an operator."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp

from strategist.ai.lead import held_intent
from strategist.ai.lead.derive import derive_ledger
from strategist.ai.lead.held_intent import hold_the_intent
from strategist.ai.lead.intent import IntentClassification, UserIntent
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
    is_blocking,
)
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
    SpecStructure,
    StructureNode,
)
from strategist.tests._support.site_organisms import recorded_organisms
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from strategist.tests.unit.domain.strategy._vaccine_request import (
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


@pytest.fixture(autouse=True)
def _recorded_organisms(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _organisms(site_id: str) -> list[str]:
        return recorded_organisms(site_id)

    monkeypatch.setattr(held_intent, "list_organisms", _organisms)


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
                quote=VACCINE[VACCINE.index("expressed") : -1],
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


async def _combination_after_build(operator: CombineOp) -> GroundedConstraint:
    state = pipeline_state(user_prompt=VACCINE)
    intent = _intent("AND")
    await hold_the_intent(lead_deps(state), intent, VACCINE)
    [held] = state.domain.requirements
    linked = [
        c.model_copy(update={"answers": [RequirementLink(requirement=held.id)]})
        for c in _CRITERIA
    ]
    state.domain.operational_spec = OperationalSpec(
        goal="vaccine candidates", criteria=linked, structure=_chain(operator)
    )
    [grounded] = [
        g
        for g in derive_ledger(state, intent).constraints.grounded
        if g.constraint.kind is ConstraintKind.COMBINATION
    ]
    return grounded


async def test_a_combination_the_message_quotes_is_the_users() -> None:
    state = pipeline_state(user_prompt=VACCINE)

    await hold_the_intent(lead_deps(state), _intent("AND"), VACCINE)

    assert [(c.source, c.hard) for c in state.domain.requirements] == [
        (ConstraintSource.USER_EXPLICIT, True),
    ]


async def test_an_intersect_build_names_its_operator() -> None:
    grounded = await _combination_after_build(CombineOp.INTERSECT)

    assert (grounded.realized_value, "meet at INTERSECT" in grounded.note) == (
        None,
        True,
    )
    assert is_blocking(grounded) is False


async def test_a_union_build_reports_its_operator_and_blocks_nothing() -> None:
    grounded = await _combination_after_build(CombineOp.UNION)

    assert (
        grounded.status,
        "meet at UNION" in grounded.note,
        is_blocking(grounded),
    ) == (
        ConstraintStatus.GROUNDED,
        True,
        False,
    )
