"""The seed measurer writes a seed file in the layout it read it in, and the
organism marks the mock arcs read are recorded from the seeds' own searches."""

from __future__ import annotations

import pytest

from pathfinder.ai.models.mock import site_values
from pathfinder.devtools import seeds
from pathfinder.devtools.seeds import marks_json, seeds_json
from pathfinder.services.experiment.seed.catalog import (
    SEED_DATABASES,
    SEEDS_DIR,
    get_seeds_for_site,
)
from pathfinder.tests._support.organism_reads import MARKS


@pytest.mark.parametrize("site_id", SEED_DATABASES)
def test_a_seed_file_is_written_back_byte_for_byte(site_id: str) -> None:
    on_disk = (SEEDS_DIR / f"{site_id}.json").read_text()

    assert seeds_json(get_seeds_for_site(site_id)) == on_disk


async def test_the_marks_are_recorded_for_every_search_the_seeds_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _record_type(_site: str, _search: str, hint: str | None) -> str:
        return hint or "transcript"

    async def _marked(_site: str, _record_type: str, search_name: str) -> str | None:
        return MARKS.get(search_name)

    monkeypatch.setattr(seeds, "resolve_search_record_type", _record_type)
    monkeypatch.setattr(seeds, "organism_parameter", _marked)

    recorded = await seeds.seed_organism_marks()

    assert sorted(recorded) == sorted(SEED_DATABASES)
    assert recorded["trichdb"] == {
        "GenesByGoTerm": "organism",
        "GenesWithSignalPeptide": "organism",
    }
    assert set(recorded["vectorbase"]) == set(site_values.recorded_marks("vectorbase"))


def test_the_marks_file_is_written_back_byte_for_byte() -> None:
    on_disk = site_values.MARKS_FILE.read_text()

    assert marks_json(site_values.recorded_marks_by_site()) == on_disk
