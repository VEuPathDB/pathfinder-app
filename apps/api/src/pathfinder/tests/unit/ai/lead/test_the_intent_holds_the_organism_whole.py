"""A turn's intent records an organism entry the message states whole."""

from __future__ import annotations

import pytest

from pathfinder.ai.lead import held_intent
from pathfinder.ai.lead.held_intent import hold_the_intent
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.tests._support.site_organisms import recorded_organisms
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

S5 = (
    "Find Anopheles gambiae PEST genes with a predicted signal peptide and 2 to 99 "
    "transmembrane domains."
)
NEOSPORA = "Carry these to their orthologs in Neospora caninum Liverpool."

# The classification the Lead recorded on turn 1 of the S5 flow on vectorbase.
_S5_SPLIT = {
    "classification": "new_strategy",
    "inferredGoal": (
        "Find Anopheles gambiae PEST genes that have a predicted signal peptide "
        "and between 2 and 99 transmembrane domains."
    ),
    "explicitConstraints": [
        {
            "hard": True,
            "kind": "organism",
            "label": "organism",
            "source": "user_explicit",
            "requestedValue": "Anopheles gambiae",
        },
        {
            "hard": True,
            "kind": "combination",
            "label": "criteria combination",
            "source": "user_explicit",
            "requestedValue": (
                "PEST genes AND genes with a predicted signal peptide AND genes "
                "with 2 to 99 transmembrane domains"
            ),
        },
        {
            "hard": True,
            "kind": "other",
            "label": "PEST gene annotation",
            "source": "user_explicit",
            "requestedValue": "PEST genes",
        },
        {
            "hard": True,
            "kind": "other",
            "label": "predicted signal peptide",
            "source": "user_explicit",
            "requestedValue": "predicted signal peptide",
        },
        {
            "hard": True,
            "kind": "other",
            "label": "transmembrane domain range",
            "source": "user_explicit",
            "requestedValue": "2 to 99 transmembrane domains",
        },
    ],
}
_S5_WHOLE = {
    **_S5_SPLIT,
    "explicitConstraints": [
        {
            "kind": "organism",
            "label": "organism",
            "source": "user_explicit",
            "requestedValue": "Anopheles gambiae PEST",
        },
        {
            "kind": "combination",
            "label": "criteria combination",
            "source": "user_explicit",
            "requestedValue": (
                "predicted signal peptide AND 2 to 99 transmembrane domains"
            ),
        },
    ],
}


@pytest.fixture
def sites_read(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The sites whose organism list was read, served from the recording."""
    read: list[str] = []

    async def _organisms(site_id: str) -> list[str]:
        read.append(site_id)
        return recorded_organisms(site_id)

    monkeypatch.setattr(held_intent, "list_organisms", _organisms)
    return read


def _deps(site_id: str, message: str) -> LeadDeps:
    return lead_deps(pipeline_state(site_id, user_prompt=message))


async def test_the_recorded_split_is_recorded_whole(sites_read: list[str]) -> None:
    deps = _deps("vectorbase", S5)

    held = await hold_the_intent(deps, UserIntent.model_validate(_S5_SPLIT), S5)

    assert [
        (c.kind.value, c.requested_value)
        for c in held.explicit_constraints
        if c.kind in {ConstraintKind.ORGANISM, ConstraintKind.OTHER}
    ] == [
        ("organism", "Anopheles gambiae PEST"),
        ("other", "PEST genes"),
        ("other", "predicted signal peptide"),
        ("other", "2 to 99 transmembrane domains"),
    ]
    assert [
        c.requested_value
        for c in deps.state.domain.requirements
        if c.kind is ConstraintKind.ORGANISM
    ] == ["Anopheles gambiae PEST"]
    assert (deps.intent, sites_read) == (held, ["vectorbase"])


async def test_the_whole_entry_is_recorded_as_stated(sites_read: list[str]) -> None:
    deps = _deps("vectorbase", S5)

    await hold_the_intent(deps, UserIntent.model_validate(_S5_WHOLE), S5)

    assert [
        c.requested_value
        for c in deps.state.domain.requirements
        if c.kind is ConstraintKind.ORGANISM
    ] == ["Anopheles gambiae PEST"]
    assert sites_read == ["vectorbase"]


async def test_a_species_without_the_stated_strain_is_completed_on_toxodb(
    sites_read: list[str],
) -> None:
    intent = UserIntent.model_validate(
        {
            "classification": "extend_strategy",
            "inferredGoal": "orthologs in Neospora",
            "explicitConstraints": [
                {
                    "kind": "organism",
                    "label": "target organism",
                    "source": "user_explicit",
                    "requestedValue": "Neospora caninum",
                },
            ],
        }
    )

    held = await hold_the_intent(_deps("toxodb", NEOSPORA), intent, NEOSPORA)

    assert [c.requested_value for c in held.explicit_constraints] == [
        "Neospora caninum Liverpool"
    ]
    assert sites_read == ["toxodb"]


async def test_an_intent_with_nothing_to_split_reads_no_organism_list(
    sites_read: list[str],
) -> None:
    deps = _deps("vectorbase", S5)
    intent = UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="PEST genes with a signal peptide",
    )

    held = await hold_the_intent(deps, intent, S5)

    assert (sites_read, held) == ([], intent)
