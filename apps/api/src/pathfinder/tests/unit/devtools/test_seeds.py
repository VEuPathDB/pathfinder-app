"""The seed measurer writes a seed file in the layout it read it in."""

from __future__ import annotations

import pytest

from pathfinder.devtools.seeds import seeds_json
from pathfinder.services.experiment.seed.catalog import (
    SEED_DATABASES,
    SEEDS_DIR,
    get_seeds_for_site,
)


@pytest.mark.parametrize("site_id", SEED_DATABASES)
def test_a_seed_file_is_written_back_byte_for_byte(site_id: str) -> None:
    on_disk = (SEEDS_DIR / f"{site_id}.json").read_text()

    assert seeds_json(get_seeds_for_site(site_id)) == on_disk
