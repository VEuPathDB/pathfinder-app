"""A message that removes a requirement retires it with its lifecycle, so a
check never reports it as a gap; a new value of its kind replaces it."""

from __future__ import annotations

from uuid import uuid4

import pytest

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import held_intent
from pathfinder.ai.lead.derive import grounded_requirements
from pathfinder.ai.lead.held_intent import hold_the_intent
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ReplacedLifecycle,
    WithdrawnLifecycle,
)
from pathfinder.tests._support.site_organisms import recorded_organisms
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_CUTOFF = requirement(ConstraintKind.PERCENTILE, "expression", "top 50th percentile")
_QUARTILE = requirement(ConstraintKind.PERCENTILE, "expression", "top quartile")
_SIGNAL = requirement(ConstraintKind.UNTYPED, "localisation", "signal peptide")


@pytest.fixture(autouse=True)
def _recorded_organisms(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _organisms(site_id: str) -> list[str]:
        return recorded_organisms(site_id)

    monkeypatch.setattr(held_intent, "list_organisms", _organisms)


async def _turn(
    domain: StrategyDomainState, message: str, intent: UserIntent
) -> LeadDeps:
    """One message of the thread, classified."""
    state = pipeline_state(
        "toxodb", user_prompt=message, user_message_id=uuid4(), domain=domain
    )
    deps = lead_deps(state, intent=None)
    await hold_the_intent(deps, intent, deps.state.user_prompt)
    return deps


def _intent(**fields: object) -> UserIntent:
    return UserIntent.model_validate(
        {"classification": IntentClassification.EDIT_STRATEGY, "inferredGoal": "g"}
        | fields
    )


def _taking_back(quote: str, number: str) -> UserIntent:
    return _intent(
        request={"withdrawn": [{"quote": quote, "requirement": number}]},
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
        _taking_back("remove the expression requirement", "R2"),
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


async def test_a_removed_cutoff_is_no_requirement_the_check_reads() -> None:
    deps = await _cutoff_stated_then_removed()

    checked = grounded_requirements(deps.state, None)

    assert [g.constraint for g in checked] == [_SIGNAL]


async def test_a_new_value_of_the_kind_replaces_the_held_one() -> None:
    domain = StrategyDomainState(requirements=[_CUTOFF])

    deps = await _turn(
        domain,
        "Swap the 50th percentile for the top quartile.",
        _intent(explicit_constraints=[_QUARTILE]),
    )

    assert deps.state.domain.requirements == [_QUARTILE]
    assert [r.lifecycle for r in deps.state.domain.retired_requirements] == [
        ReplacedLifecycle(by=_QUARTILE.id)
    ]


async def test_a_number_the_thread_does_not_hold_retires_nothing() -> None:
    domain = StrategyDomainState(requirements=[_SIGNAL])

    deps = await _turn(
        domain,
        "Drop the exported requirement.",
        _taking_back("Drop the exported requirement", "R2"),
    )

    assert (
        deps.state.domain.requirements,
        deps.state.domain.retired_requirements,
        None if deps.intent is None else deps.intent.withdrawn_ids,
    ) == ([_SIGNAL], [], [])


async def test_a_no_on_the_removal_card_takes_the_withdrawal_back() -> None:
    """The a16 delete path: the message that drops a step is declined on its card."""
    deps = await _cutoff_stated_then_removed()

    deps.state.domain.withdraw_this_messages_requirements()

    assert deps.state.domain.requirements == [_SIGNAL, _CUTOFF]
    assert deps.state.domain.retired_requirements == []


async def test_a_withdrawal_retires_the_numbered_requirement_in_its_source() -> None:
    genus = requirement(ConstraintKind.ORGANISM, "Organism", "Cryptosporidium")
    assumed = genus.model_copy(update={"source": ConstraintSource.ASSUMED})
    record_type = Constraint(
        kind=ConstraintKind.RECORD_TYPE,
        label="record type",
        requested_value="genes",
        source=ConstraintSource.ASSUMED,
    )
    domain = StrategyDomainState(requirements=[assumed, _SIGNAL, record_type])

    deps = await _turn(
        domain,
        "Drop the gene restriction.",
        _taking_back("Drop the gene restriction", "R2"),
    )

    assert (
        None if deps.intent is None else deps.intent.withdrawn_ids,
        [r.constraint for r in deps.state.domain.retired_requirements],
    ) == ([record_type.id], [record_type])


async def test_a_requirement_stated_again_is_live_again() -> None:
    deps = await _cutoff_stated_then_removed()

    restated = await _turn(
        deps.state.domain,
        "Actually keep the top 50th percentile of expression.",
        _intent(explicit_constraints=[_CUTOFF]),
    )

    assert restated.state.domain.retired_requirements == []
    assert _CUTOFF in restated.state.domain.requirements
