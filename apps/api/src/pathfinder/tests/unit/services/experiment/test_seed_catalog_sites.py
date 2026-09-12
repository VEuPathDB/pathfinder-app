"""The seed catalog reads the site registry, and ships a file for every site it lists."""

from __future__ import annotations

import pytest
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import load_sites_config

from pathfinder.services.experiment.seed.catalog import (
    SEED_DATABASES,
    get_all_seeds,
    get_seeds_for_site,
)


def test_the_seed_sites_come_from_the_registry() -> None:
    registered = list(load_sites_config().sites)
    assert [site for site in registered if site in SEED_DATABASES] == SEED_DATABASES
    assert set(SEED_DATABASES) <= set(registered)


def test_a_registered_site_that_ships_no_seed_is_refused() -> None:
    """A site with no seed file answers a refusal, never a read of a missing file."""
    registered = set(load_sites_config().sites)
    seedless = sorted(registered - set(SEED_DATABASES))
    assert seedless == ["trichdb"]

    with pytest.raises(VEuPathDBError) as refusal:
        get_seeds_for_site("trichdb")

    assert refusal.value.code.value == "SITE_NOT_FOUND"


def test_every_listed_site_reads() -> None:
    assert len(get_all_seeds()) > 0
    for site in SEED_DATABASES:
        assert get_seeds_for_site(site) is not None
