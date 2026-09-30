"""A withdrawal with no successor is a plain removal; the gate's refusal names
only the key at fault, and a successor the thread already holds is refused."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.classification_gate import SiteReading, classification_refusal
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.domain.strategy.requirement_lifecycle import RequirementWithdrawal
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state, requirement

_MESSAGE = (
    "put my strategy back to the DAL972 genes alone, without the TREU927 search "
    "or the union."
)
_DAL972 = requirement(
    ConstraintKind.ORGANISM, "organism", "Trypanosoma brucei gambiense DAL972"
)
_TREU927 = requirement(
    ConstraintKind.ORGANISM, "reference strain", "Trypanosoma brucei brucei TREU927"
)
_DOMAINS = requirement(ConstraintKind.OTHER, "domain annotation", "RNA-binding domain")
_HOLDS = (
    " The requirements it holds: 'organism:Trypanosoma brucei gambiense DAL972', "
    "'other:RNA-binding domain', 'organism:Trypanosoma brucei brucei TREU927'. An "
    "empty replacedBy removes the requirement; a replacedBy names a requirement "
    "this message states for the first time."
)
_UNION = (
    "combination:Trypanosoma brucei gambiense DAL972 genes OR Trypanosoma brucei "
    "brucei TREU927 genes"
)


def _refusal(withdrawals: list[RequirementWithdrawal], stated: list[Constraint]) -> str:
    """The gate's refusal of the withdrawals, empty when it accepts them."""
    state = pipeline_state(
        "tritrypdb",
        user_prompt=_MESSAGE,
        user_message_id=uuid4(),
        domain=StrategyDomainState(requirements=[_DAL972, _DOMAINS, _TREU927]),
    )
    intent = UserIntent(
        classification=IntentClassification.EDIT_STRATEGY,
        inferred_goal="Restore the DAL972 genes alone.",
        explicit_constraints=stated,
        withdrawn_requirements=withdrawals,
    )
    return classification_refusal(state, intent, SiteReading()) or ""


def test_a_plain_removal_is_accepted() -> None:
    assert _refusal([RequirementWithdrawal(key=_TREU927.key)], []) == ""


def test_an_unheld_key_is_refused_without_asking_for_a_successor() -> None:
    refusal = _refusal(
        [RequirementWithdrawal(key=_TREU927.key), RequirementWithdrawal(key=_UNION)],
        [],
    )

    assert refusal == (
        f"withdrawn_requirements: {_UNION!r} names no requirement the "
        f"conversation holds.{_HOLDS}"
    )


def test_a_successor_the_thread_already_holds_is_refused() -> None:
    refusal = _refusal(
        [RequirementWithdrawal(key=_TREU927.key, replaced_by=_DAL972.key)],
        [_DAL972, _DOMAINS],
    )

    assert refusal == (
        f"withdrawn_requirements: {_DAL972.key!r} is a requirement the "
        f"conversation already holds, so it replaces nothing.{_HOLDS}"
    )


def test_a_successor_the_message_does_not_state_is_refused() -> None:
    successor = "organism:Trypanosoma brucei gambiense STIB386"

    refusal = _refusal(
        [RequirementWithdrawal(key=_TREU927.key, replaced_by=successor)], []
    )

    assert refusal == (
        f"withdrawn_requirements: {successor!r} replaces it, but "
        f"explicit_constraints states no such requirement.{_HOLDS}"
    )


def test_an_edit_that_compares_its_two_values_keeps_its_successor() -> None:
    """The hostdb edit from chromosome 17 to 19 that also asks the count."""
    chromosome_17 = requirement(ConstraintKind.OTHER, "chromosome", "chromosome 17")
    chromosome_19 = requirement(ConstraintKind.OTHER, "chromosome", "chromosome 19")
    state = pipeline_state(
        "hostdb",
        user_prompt="Change chromosome 17 to chromosome 19 and tell me the count.",
        user_message_id=uuid4(),
        domain=StrategyDomainState(requirements=[chromosome_17]),
    )
    intent = UserIntent(
        classification=IntentClassification.EDIT_STRATEGY,
        inferred_goal="Change chromosome 17 to chromosome 19.",
        is_differential=True,
        differential_sides=["chromosome 17", "chromosome 19"],
        explicit_constraints=[chromosome_19],
        withdrawn_requirements=[
            RequirementWithdrawal(key=chromosome_17.key, replaced_by=chromosome_19.key)
        ],
    )

    assert classification_refusal(state, intent, SiteReading()) is None
    assert intent.explicit_constraints == [chromosome_19]
