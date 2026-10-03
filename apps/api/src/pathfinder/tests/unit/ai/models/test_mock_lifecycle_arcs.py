"""The lifecycle arcs state requirements with no key and no successor, and the
thread derives the replacement and the withdrawal from what it holds."""

from __future__ import annotations

from uuid import uuid4

import pytest

from pathfinder.ai.graph.thread_requirements import ThreadRequirements
from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.ai.lead.intent import UserIntent
from pathfinder.ai.models.mock.lifecycle_arcs import WITHDRAWN_VALUE
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ReplacedLifecycle,
)
from pathfinder.tests.unit.ai.models._mock_turns import args_of, names, play

SITES = ("plasmodb", "vectorbase")


def _stated(kind: ConstraintKind, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        label=kind.value,
        source=ConstraintSource.USER_EXPLICIT,
    )


def _played(site_id: str, message: str) -> UserIntent:
    calls = play("lead", site_id, message)
    assert names(calls) == ["classify_user_intent", "final_result"]
    [classified] = args_of(calls, "classify_user_intent")
    return UserIntent.model_validate(classified["intent"])


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
        [ReplacedLifecycle(by=f"organism:{organism}")],
    )


@pytest.mark.parametrize("site_id", SITES)
def test_a_withdrawn_statement_retires_the_requirement_it_names(site_id: str) -> None:
    tm = _stated(ConstraintKind.OTHER, f"a {WITHDRAWN_VALUE}")
    signal = _stated(ConstraintKind.OTHER, "a signal peptide")
    message = "Drop the transmembrane domain. [[arc:withdrawn-requirement]]"

    thread = _recorded([tm, signal], message, _played(site_id, message))

    assert (
        thread.requirements,
        [(r.constraint, r.lifecycle.state) for r in thread.retired_requirements],
    ) == ([signal], [(tm, "withdrawn")])
