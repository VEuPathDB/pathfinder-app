"""A combination the message quotes is held to the operator the strategy builds."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead import held_intent
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.held_intent import hold_the_intent
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
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
from pathfinder.tests._support.site_organisms import recorded_organisms
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
    state.domain.operational_spec = OperationalSpec(
        goal="vaccine candidates", criteria=_CRITERIA, structure=_chain(operator)
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


async def test_an_intersect_build_honors_the_stated_and() -> None:
    grounded = await _combination_after_build(CombineOp.INTERSECT)

    assert grounded.status is ConstraintStatus.GROUNDED
    assert grounded.realized_value == "INTERSECT"
    assert is_blocking(grounded) is False


async def test_a_union_build_breaks_the_stated_and() -> None:
    grounded = await _combination_after_build(CombineOp.UNION)

    assert grounded.status is ConstraintStatus.UNGROUNDABLE
    assert is_blocking(grounded) is True
