"""The classification gate holds an off-topic classification to the record types
the site's loaded catalog names."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.wdk import WDKRecordType
from veupathdb_mcp.catalog import get_discovery_service

from pathfinder.ai.lead import classification_gate
from pathfinder.ai.lead.intent import ClassifiedIntent, IntentClassification, UserIntent
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

SITE = "giardiadb"
LANTERNS = WDKRecordType(
    url_segment="lantern",
    display_name="Lantern",
    display_name_plural="Lanterns",
)
HARBOR_LIGHTS = WDKRecordType(
    url_segment="harborlight",
    display_name="Harbor Light",
    display_name_plural="Harbor Lights",
)


@pytest.fixture(autouse=True)
def _site_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    held = [LANTERNS, HARBOR_LIGHTS]

    def _held(site_id: str) -> list[WDKRecordType] | None:
        return held if site_id == SITE else None

    async def _organisms(site_id: str) -> list[str]:
        return []

    monkeypatch.setattr(get_discovery_service(), "held_record_types", _held)
    monkeypatch.setattr(classification_gate, "list_organisms", _organisms)


async def _classify(message: str, classification: str) -> ClassifiedIntent:
    state = pipeline_state(SITE, user_prompt=message)
    ctx = run_context_for(lead_deps(state), tool_call_id="call_classify")
    intent = UserIntent.model_validate(
        {"classification": classification, "inferredGoal": "the goal"}
    )
    returned = await classify_user_intent(ctx, intent)
    return ClassifiedIntent.model_validate(returned.return_value)


async def test_a_message_naming_a_record_type_of_the_site_is_not_off_topic() -> None:
    with pytest.raises(ModelRetry) as refused:
        await _classify("Which lanterns have the longest names?", "off_topic")

    assert str(refused.value) == (
        'The message names "Lanterns", a record type of this site, so it is in '
        "scope. This site's records are: Lantern (Lanterns), Harbor Light "
        "(Harbor Lights). Classify it by what it asks of them."
    )


async def test_a_record_type_of_two_words_is_read_as_one_run() -> None:
    with pytest.raises(ModelRetry) as refused:
        await _classify("List every harbor light you hold.", "off_topic")

    assert str(refused.value).startswith('The message names "Harbor Light", a')


async def test_the_words_of_a_record_type_apart_name_nothing() -> None:
    classified = await _classify("A light by the harbor at night.", "off_topic")

    assert classified.intent.classification is IntentClassification.OFF_TOPIC


async def test_a_message_naming_no_record_type_stays_off_topic() -> None:
    classified = await _classify("Write a haiku about spring.", "off_topic")

    assert classified.intent.classification is IntentClassification.OFF_TOPIC


async def test_a_site_with_no_loaded_catalog_names_no_record_type() -> None:
    state = pipeline_state("toxodb", user_prompt="Which lanterns glow?")
    ctx = run_context_for(lead_deps(state), tool_call_id="call_classify")
    intent = UserIntent.model_validate(
        {"classification": "off_topic", "inferredGoal": "the goal"}
    )

    returned = await classify_user_intent(ctx, intent)

    held = ClassifiedIntent.model_validate(returned.return_value)
    assert held.intent.classification is IntentClassification.OFF_TOPIC
