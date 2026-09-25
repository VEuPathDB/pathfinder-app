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


def test_every_registered_site_ships_seeds() -> None:
    assert sorted(set(load_sites_config().sites) - set(SEED_DATABASES)) == []


def test_a_site_the_registry_does_not_name_is_refused() -> None:
    """An unknown id answers a refusal, never a read of a missing file."""
    with pytest.raises(VEuPathDBError) as refusal:
        get_seeds_for_site("nosuchdb")

    assert refusal.value.code.value == "SITE_NOT_FOUND"


def test_every_listed_site_reads() -> None:
    assert len(get_all_seeds()) > 0
    for site in SEED_DATABASES:
        assert get_seeds_for_site(site) is not None
