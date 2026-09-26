"""The classification gate refuses an organism entry the message states whole but splits."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.lead import lead_tools
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.tests._support.run_context import run_context_for
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
    """The sites whose organism list the gate read, served from the recording."""
    read: list[str] = []

    async def _organisms(site_id: str) -> list[str]:
        read.append(site_id)
        return recorded_organisms(site_id)

    monkeypatch.setattr(lead_tools, "list_organisms", _organisms)
    return read


async def test_the_recorded_split_is_refused_with_the_entry_named(
    sites_read: list[str],
) -> None:
    state = pipeline_state("vectorbase", user_prompt=S5)
    ctx = run_context_for(lead_deps(state), tool_call_id="call_classify")

    with pytest.raises(ModelRetry) as refused:
        await classify_user_intent(ctx, UserIntent.model_validate(_S5_SPLIT))

    assert str(refused.value) == (
        'The message names the organism "Anopheles gambiae PEST", one entry of '
        "this site's organism list. Record it whole as the organism constraint; "
        '"PEST" is part of its name, not a requirement of its own.'
    )
    assert sites_read == ["vectorbase"]
    assert state.domain.requirements == []
    assert ctx.deps.intent is None


async def test_the_whole_entry_is_recorded_as_the_organism(
    sites_read: list[str],
) -> None:
    state = pipeline_state("vectorbase", user_prompt=S5)
    ctx = run_context_for(lead_deps(state), tool_call_id="call_classify")

    await classify_user_intent(ctx, UserIntent.model_validate(_S5_WHOLE))

    assert [
        c.requested_value
        for c in state.domain.requirements
        if c.kind is ConstraintKind.ORGANISM
    ] == ["Anopheles gambiae PEST"]
    assert sites_read == ["vectorbase"]


async def test_a_species_without_the_stated_strain_is_refused_on_toxodb(
    sites_read: list[str],
) -> None:
    state = pipeline_state("toxodb", user_prompt=NEOSPORA)
    ctx = run_context_for(lead_deps(state), tool_call_id="call_classify")
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

    with pytest.raises(ModelRetry) as refused:
        await classify_user_intent(ctx, intent)

    assert '"Liverpool" is part of its name' in str(refused.value)
    assert sites_read == ["toxodb"]


async def test_the_strain_as_a_combination_term_is_refused(
    sites_read: list[str],
) -> None:
    state = pipeline_state("vectorbase", user_prompt=S5)
    ctx = run_context_for(lead_deps(state), tool_call_id="call_classify")
    retry = {
        **_S5_WHOLE,
        "explicitConstraints": [
            {
                "kind": "combination",
                "label": "criteria combination",
                "source": "user_explicit",
                "requestedValue": (
                    "PEST genes AND predicted signal peptide AND 2 to 99 "
                    "transmembrane domains"
                ),
            },
        ],
    }

    with pytest.raises(ModelRetry) as refused:
        await classify_user_intent(ctx, UserIntent.model_validate(retry))

    assert '"PEST" is part of its name' in str(refused.value)
    assert sites_read == ["vectorbase"]


async def test_an_intent_with_nothing_to_split_reads_no_organism_list(
    sites_read: list[str],
) -> None:
    state = pipeline_state("vectorbase", user_prompt=S5)
    ctx = run_context_for(lead_deps(state), tool_call_id="call_classify")
    intent = UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="PEST genes with a signal peptide",
    )

    await classify_user_intent(ctx, intent)

    assert sites_read == []
    assert ctx.deps.intent is intent
