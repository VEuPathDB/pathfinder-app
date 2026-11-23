"""Shared fixtures for unit tests."""

from collections.abc import Iterator

import pytest
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from strategist.domain.strategy.session import StrategyGraph
from strategist.platform.config import get_settings
from strategist.tests._support.declared_record_types import (
    serve_declared_record_types,
)
from strategist.tests._support.network_guard import refuse_every_connection
from strategist.tests._support.organism_reads import serve_catalog_marks
from strategist.tests._support.record_classes import serve_record_classes
from strategist.tests._support.site_organisms import serve_planned_organisms

# Input screening.


@pytest.fixture
def input_screening_enabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Turns input screening on for one test."""
    monkeypatch.setenv("INPUT_SCREENING_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def input_screening_disabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Turns input screening off for one test."""
    monkeypatch.setenv("INPUT_SCREENING_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# Network guard.


@pytest.fixture(autouse=True)
def _no_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuses network connections for the duration of a unit test.

    A test that needs a real connection carries the `allow_network` marker.
    """
    if request.node.get_closest_marker("allow_network") is None:
        refuse_every_connection(monkeypatch, request.node.nodeid)


@pytest.fixture(autouse=True)
def _catalog_marks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answers each search's organism parameter, record classes and site
    organisms from recorded catalog answers."""
    serve_catalog_marks(monkeypatch)
    serve_record_classes(monkeypatch)
    serve_planned_organisms(monkeypatch)
    serve_declared_record_types(monkeypatch)


def populate_graph(graph: StrategyGraph, *steps: StrategyStepNode) -> None:
    """Add steps to graph bypassing single-root invariant for test setup."""
    for step in steps:
        graph.steps.update(flatten_tree(step))
    graph.recompute_roots()
