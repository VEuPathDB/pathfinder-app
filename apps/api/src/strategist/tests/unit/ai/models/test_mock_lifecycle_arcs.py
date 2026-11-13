"""The lifecycle arcs state requirements with no successor and withdraw one by
its number, and the thread derives the replacement and the withdrawal."""

from __future__ import annotations

from uuid import uuid4

import pytest

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.graph.thread_requirements import ThreadRequirements
from strategist.ai.graph.turn_records import TurnMarkers
from strategist.ai.lead.held_intent import hold_the_intent
from strategist.ai.lead.intent import UserIntent
from strategist.ai.models.mock.reading import scripted_intent
from strategist.ai.models.mock.site_values import SiteValues
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ReplacedLifecycle,
)
from strategist.tests._support.site_organisms import serve_recorded_organisms
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from strategist.tests.unit.ai.models._mock_turns import names, play

SITES = ("plasmodb", "vectorbase")


def _stated(kind: ConstraintKind, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        label=kind.value,
        source=ConstraintSource.USER_EXPLICIT,
    )


def _played(site_id: str, message: str) -> UserIntent:
    assert names(play("lead", site_id, message)) == ["final_result"]
    return scripted_intent(pipeline_state(site_id, user_prompt=message), message)


def _recorded(
    held: list[Constraint], message: str, intent: UserIntent
) -> ThreadRequirements:
    thread = ThreadRequirements(
        turn_markers=TurnMarkers(message_id=uuid4()), requirements=held
    )
    thread.record(intent, [message])
    return thread


@pytest.mark.parametrize("site_id", SITES)
def test_a_narrower_organism_replaces_the_genus_the_thread_held(site_id: str) -> None:
    organism = SiteValues.for_site(site_id).organism
    genus = _stated(ConstraintKind.ORGANISM, organism.split()[0])
    message = f"Narrow that to {organism}. [[arc:narrowed-organism]]"

    thread = _recorded([genus], message, _played(site_id, message))

    assert (
        [(c.kind, c.requested_value) for c in thread.requirements],
        [r.lifecycle for r in thread.retired_requirements],
    ) == (
        [(ConstraintKind.ORGANISM, organism)],
        [ReplacedLifecycle(by=thread.requirements[0].id)],
    )


@pytest.mark.parametrize("site_id", SITES)
async def test_a_withdrawal_retires_the_requirement_its_number_names(
    site_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    serve_recorded_organisms(monkeypatch)
    tm = _stated(ConstraintKind.UNTYPED, "a transmembrane domain")
    signal = _stated(ConstraintKind.UNTYPED, "a signal peptide")
    message = "Drop the transmembrane domain. [[arc:withdrawn-requirement]]"
    assert names(play("lead", site_id, message)) == ["final_result"]
    state = pipeline_state(
        site_id,
        user_prompt=message,
        user_message_id=uuid4(),
        domain=StrategyDomainState(requirements=[tm, signal]),
    )
    deps = lead_deps(state)

    await hold_the_intent(deps, scripted_intent(state, message), message)

    assert (
        state.domain.requirements,
        [(r.constraint, r.lifecycle.state) for r in state.domain.retired_requirements],
    ) == ([signal], [(tm, "withdrawn")])
