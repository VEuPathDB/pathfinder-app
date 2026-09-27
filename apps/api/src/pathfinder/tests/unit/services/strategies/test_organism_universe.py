"""The genes of an organism value set, counted once per site, record type and
set by the site's organism search."""

from __future__ import annotations

import pytest

from pathfinder.services.strategies import organism_params
from pathfinder.services.strategies.organism_universe import universe_counts
from pathfinder.tests._support.organism_reads import serve_universe_counts

PEST = "Anopheles gambiae PEST"
STEPHENSI = "Anopheles stephensi Indian"
Asked = list[tuple[str, str, str, tuple[str, ...]]]


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> Asked:
    """The genes each organism set holds, as vectorbase's organism search counts
    them; the count of the stephensi set does not arrive."""
    return serve_universe_counts(
        monkeypatch,
        {(PEST,): 13_845, (STEPHENSI,): None, (PEST, STEPHENSI): 27_902},
    )


async def test_each_value_set_is_counted_on_the_organism_parameter(
    counted: Asked,
) -> None:
    found = await universe_counts(
        "vectorbase", "transcript", [(PEST, STEPHENSI), (PEST,)]
    )

    assert found == {(PEST,): 13_845, (PEST, STEPHENSI): 27_902}
    assert counted == [
        ("vectorbase", "transcript", "GenesByTaxon", (PEST,)),
        ("vectorbase", "transcript", "GenesByTaxon", (PEST, STEPHENSI)),
    ]


async def test_a_value_set_counted_once_is_read_from_the_cache(
    counted: Asked,
) -> None:
    await universe_counts("vectorbase", "transcript", [(PEST,)])
    again = await universe_counts("vectorbase", "transcript", [(PEST,), (PEST,)])

    assert again == {(PEST,): 13_845}
    assert len(counted) == 1


async def test_the_cache_keys_on_the_site_and_the_record_type(
    counted: Asked,
) -> None:
    await universe_counts("vectorbase", "transcript", [(PEST,)])
    await universe_counts("veupathdb", "transcript", [(PEST,)])
    await universe_counts("veupathdb", "gene", [(PEST,)])

    assert [(site, record) for site, record, *_ in counted] == [
        ("vectorbase", "transcript"),
        ("veupathdb", "transcript"),
        ("veupathdb", "gene"),
    ]


async def test_a_count_that_did_not_arrive_is_absent_and_asked_again(
    counted: Asked,
) -> None:
    first = await universe_counts("vectorbase", "transcript", [(STEPHENSI,)])
    second = await universe_counts("vectorbase", "transcript", [(STEPHENSI,)])

    assert (first, second, len(counted)) == ({}, {}, 2)


async def test_no_value_set_asks_nothing(counted: Asked) -> None:
    assert await universe_counts("vectorbase", "transcript", []) == {}
    assert counted == []


async def test_a_site_whose_organism_search_marks_no_organism_counts_nothing(
    monkeypatch: pytest.MonkeyPatch, counted: Asked
) -> None:
    async def _unmarked(_site: str, _record_type: str, _search: str) -> str | None:
        return None

    monkeypatch.setattr(organism_params, "organism_parameter", _unmarked)

    assert await universe_counts("orthomcl", "sequence", [(PEST,)]) == {}
    assert counted == []
