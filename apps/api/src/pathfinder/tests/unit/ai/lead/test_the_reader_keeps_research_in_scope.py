from __future__ import annotations

from pathfinder.ai.lead.message_reader import reading_guide


def test_the_guide_names_the_research_partner_and_the_builder() -> None:
    intro = reading_guide().intro

    assert "research partner" in intro
    assert "literature and web search" in intro
    assert "builds VEuPathDB search strategies" in intro


def test_off_topic_keeps_the_biology_and_its_literature_in_scope() -> None:
    off_topic = reading_guide().flags["off_topic"]

    assert "pathogens, hosts and vectors the VEuPathDB sites cover" in off_topic
    assert "the literature and methods about them" in off_topic
    assert "is not `off_topic`" in off_topic


def test_off_topic_names_what_is_unrelated() -> None:
    off_topic = reading_guide().flags["off_topic"]

    assert "a recipe" in off_topic
    assert "help with code" in off_topic
