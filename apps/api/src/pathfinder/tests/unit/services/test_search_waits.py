from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from veupathdb.wdk import SearchKind, SearchRequest

from pathfinder.services.search_waits import (
    TurnStatusWaits,
    runs_on_the_deployment_line,
    waiting_for,
)
from pathfinder.services.strategies import slow_searches


def _request(
    *names: str, site_id: str = "plasmodb", kind: SearchKind = "report"
) -> SearchRequest:
    return SearchRequest(site_id=site_id, kind=kind, search_names=frozenset(names))


@pytest.fixture
def a_slow_percentile_search() -> Iterator[None]:
    slow_searches._SLOW_SEARCHES[("plasmodb", "GenesByPercentile")] = True
    yield
    slow_searches._SLOW_SEARCHES.clear()


def test_a_high_speed_snp_search_runs_on_the_deployment_line() -> None:
    assert runs_on_the_deployment_line(_request("GenesByNgsSnps")) is True


@pytest.mark.usefixtures("a_slow_percentile_search")
def test_a_search_marked_slow_runs_on_the_line_of_its_own_site_only() -> None:
    assert runs_on_the_deployment_line(_request("GenesByPercentile")) is True
    assert (
        runs_on_the_deployment_line(_request("GenesByPercentile", site_id="toxodb"))
        is False
    )


@pytest.mark.parametrize("kind", ["report", "step", "strategy", "analysis"])
def test_a_high_speed_snp_search_holds_the_line_on_every_request(
    kind: SearchKind,
) -> None:
    assert runs_on_the_deployment_line(_request("GenesByNgsSnps", kind=kind)) is True


@pytest.mark.usefixtures("a_slow_percentile_search")
def test_a_search_marked_slow_holds_the_line_on_its_own_count() -> None:
    assert runs_on_the_deployment_line(_request("GenesByPercentile")) is True


@pytest.mark.usefixtures("a_slow_percentile_search")
@pytest.mark.parametrize("kind", ["step", "strategy", "analysis"])
def test_a_request_on_a_tree_that_names_a_search_marked_slow_does_not_wait(
    kind: SearchKind,
) -> None:
    assert (
        runs_on_the_deployment_line(_request("GenesByPercentile", kind=kind)) is False
    )


@pytest.mark.usefixtures("a_slow_percentile_search")
def test_a_read_of_a_tree_with_a_snp_search_beside_a_slow_one_waits() -> None:
    request = _request("GenesByPercentile", "GenesByNgsSnps", kind="strategy")

    assert runs_on_the_deployment_line(request) is True


def test_any_other_search_does_not() -> None:
    assert runs_on_the_deployment_line(_request("GenesByText")) is False
    assert runs_on_the_deployment_line(_request()) is False


@pytest.mark.parametrize(
    ("site_id", "said"),
    [
        ("plasmodb", "Waiting for PlasmoDB"),
        ("vectorbase", "Waiting for VectorBase"),
        ("veupathdb", "Waiting for VEuPathDB"),
    ],
)
def test_a_wait_names_the_site_as_its_researchers_know_it(
    site_id: str, said: str
) -> None:
    assert waiting_for(site_id) == said


@dataclass
class _Writer:
    conversation_id: UUID = field(default_factory=uuid4)
    turn_id: UUID = field(default_factory=uuid4)
    chunks: list[dict[str, Any]] = field(default_factory=list)

    async def write(self, chunk: dict[str, Any]) -> int:
        self.chunks.append(chunk)
        return len(self.chunks)


async def test_a_turn_says_it_waits_and_clears_the_notice_when_the_search_starts() -> (
    None
):
    writer = _Writer()
    waits = TurnStatusWaits(writer)

    await waits.waiting("plasmodb")
    await waits.running("plasmodb")

    assert [c["data"] for c in writer.chunks] == [
        {"label": "Waiting for PlasmoDB", "waitingOnLlm": False},
        {"label": "", "waitingOnLlm": False},
    ]
