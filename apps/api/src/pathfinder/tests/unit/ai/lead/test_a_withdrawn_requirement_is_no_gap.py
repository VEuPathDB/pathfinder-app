"""A message that removes a requirement retires it with its lifecycle, so a
check never reports it as a gap; a new value of its kind replaces it."""

from __future__ import annotations

from uuid import uuid4

import pytest

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import classification_gate
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import _findings
from pathfinder.domain.caveats import RequirementGap
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ReplacedLifecycle,
    WithdrawnLifecycle,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests._support.site_organisms import recorded_organisms
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_CUTOFF = requirement(ConstraintKind.PERCENTILE, "expression", "top 50th percentile")
_QUARTILE = requirement(ConstraintKind.PERCENTILE, "expression", "top quartile")
_SIGNAL = requirement(ConstraintKind.OTHER, "localisation", "signal peptide")
# The requirement as the classifier states what the message takes back.
_EXPRESSION = requirement(ConstraintKind.PERCENTILE, "expression", "expression")


@pytest.fixture(autouse=True)
def _recorded_organisms(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _organisms(site_id: str) -> list[str]:
        return recorded_organisms(site_id)

    monkeypatch.setattr(classification_gate, "list_organisms", _organisms)


async def _turn(
    domain: StrategyDomainState, message: str, intent: UserIntent
) -> LeadDeps:
    """One message of the thread, classified."""
    state = pipeline_state(
        "toxodb", user_prompt=message, user_message_id=uuid4(), domain=domain
    )
    deps = lead_deps(state, intent=None)
    await classify_user_intent(run_context_for(deps, "t_classify"), intent)
    return deps


def _intent(**fields: object) -> UserIntent:
    return UserIntent.model_validate(
        {"classification": IntentClassification.EDIT_STRATEGY, "inferredGoal": "g"}
        | fields
    )


def _review() -> VerificationReview:
    return VerificationReview(
        requirements=[
            RequirementCheck(
                text="top 50th percentile expression",
                turn=2,
                how="parameter",
                status="unmet",
            ),
            RequirementCheck(
                text="signal peptide", turn=1, how="search", status="unmet"
            ),
        ]
    )


async def _cutoff_stated_then_removed() -> LeadDeps:
    """Turn 2 states a cutoff; turn 4 removes it."""
    domain = StrategyDomainState(requirements=[_SIGNAL])
    stated = await _turn(
        domain,
        "Also require the top 50th percentile of expression.",
        _intent(explicit_constraints=[_CUTOFF]),
    )
    return await _turn(
        stated.state.domain,
        "Please remove the expression requirement.",
        _intent(withdrawn=[_EXPRESSION]),
    )


async def test_a_removed_cutoff_leaves_the_live_requirements() -> None:
    deps = await _cutoff_stated_then_removed()
    domain = deps.state.domain

    assert domain.requirements == [_SIGNAL]
    assert [(r.constraint, r.lifecycle) for r in domain.retired_requirements] == [
        (
            _CUTOFF,
            WithdrawnLifecycle(turn_id=str(deps.state.user_message_id)),
        )
    ]


async def test_a_removed_cutoff_is_no_gap_after_the_check() -> None:
    deps = await _cutoff_stated_then_removed()

    gaps = _findings(deps, _review(), []).gaps

    assert gaps == [RequirementGap(text="signal peptide", status="unmet")]


async def test_a_new_value_of_the_kind_replaces_the_held_one() -> None:
    domain = StrategyDomainState(requirements=[_CUTOFF])

    deps = await _turn(
        domain,
        "Swap the 50th percentile for the top quartile.",
        _intent(explicit_constraints=[_QUARTILE]),
    )

    assert deps.state.domain.requirements == [_QUARTILE]
    assert [r.lifecycle for r in deps.state.domain.retired_requirements] == [
        ReplacedLifecycle(by=_QUARTILE.key)
    ]


async def test_a_withdrawal_of_a_requirement_the_thread_lacks_retires_nothing() -> None:
    domain = StrategyDomainState(requirements=[_SIGNAL])
    exported = requirement(ConstraintKind.OTHER, "localisation", "exported")

    deps = await _turn(
        domain, "Drop the exported requirement.", _intent(withdrawn=[exported])
    )

    assert (deps.state.domain.requirements, deps.state.domain.retired_requirements) == (
        [_SIGNAL],
        [],
    )


async def test_a_no_on_the_removal_card_takes_the_withdrawal_back() -> None:
    """The a16 delete path: the message that drops a step is declined on its card."""
    deps = await _cutoff_stated_then_removed()

    deps.state.domain.withdraw_this_messages_requirements()

    assert deps.state.domain.requirements == [_SIGNAL, _CUTOFF]
    assert deps.state.domain.retired_requirements == []


def _as_classified(held: Constraint) -> Constraint:
    """The withdrawn requirement as the classifier typed it, with no source."""
    return Constraint(
        kind=held.kind, label=held.label, requested_value=held.requested_value
    )


async def test_a_withdrawal_keeps_the_source_the_thread_recorded() -> None:
    genus = requirement(ConstraintKind.ORGANISM, "Organism", "Cryptosporidium")
    domain = StrategyDomainState(requirements=[genus, _SIGNAL])

    deps = await _turn(
        domain,
        "Drop the Cryptosporidium restriction.",
        _intent(withdrawn=[_as_classified(genus)]),
    )

    assert deps.intent is not None
    assert [(c.requested_value, c.source) for c in deps.intent.withdrawn] == [
        ("Cryptosporidium", ConstraintSource.USER_EXPLICIT)
    ]


async def test_a_withdrawal_of_a_requirement_the_thread_lacks_keeps_its_source() -> (
    None
):
    exported = _as_classified(
        requirement(ConstraintKind.OTHER, "localisation", "exported")
    )

    deps = await _turn(
        StrategyDomainState(requirements=[_SIGNAL]),
        "Drop the exported requirement.",
        _intent(withdrawn=[exported]),
    )

    assert deps.intent is not None
    assert deps.intent.withdrawn == [exported]


async def test_a_requirement_stated_again_is_live_again() -> None:
    deps = await _cutoff_stated_then_removed()

    restated = await _turn(
        deps.state.domain,
        "Actually keep the top 50th percentile of expression.",
        _intent(explicit_constraints=[_CUTOFF]),
    )

    assert restated.state.domain.retired_requirements == []
    assert _CUTOFF in restated.state.domain.requirements
