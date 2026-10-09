"""The seed catalog reads the site list in force, and ships a file for every site it lists."""

from __future__ import annotations

import pytest
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import load_sites_config

from pathfinder.platform.config import get_settings
from pathfinder.platform.paths import REPO_ROOT
from pathfinder.platform.stage_sites import use_sites_file
from pathfinder.services.experiment.seed.catalog import (
    get_seeds_for_site,
    seed_databases,
)


def _configured() -> list[str]:
    return list(load_sites_config(get_settings().veupathdb_sites_config).sites)


def test_the_seed_sites_come_from_the_list_in_force() -> None:
    registered = _configured()
    assert [site for site in registered if site in seed_databases()] == seed_databases()
    assert set(seed_databases()) <= set(registered)


def test_every_listed_site_ships_seeds() -> None:
    assert sorted(set(_configured()) - set(seed_databases())) == []


@pytest.mark.usefixtures("restored_sites_file")
def test_a_deployment_that_serves_fewer_sites_seeds_only_those() -> None:
    use_sites_file(str(REPO_ROOT / "e2e-sites.yaml"))

    assert seed_databases() == [
        "veupathdb",
        "plasmodb",
        "toxodb",
        "cryptodb",
        "tritrypdb",
        "fungidb",
        "vectorbase",
    ]


def test_a_site_the_registry_does_not_name_is_refused() -> None:
    """An unknown id answers a refusal, never a read of a missing file."""
    with pytest.raises(VEuPathDBError) as refusal:
        get_seeds_for_site("nosuchdb")

    assert refusal.value.code.value == "SITE_NOT_FOUND"


def test_every_listed_site_reads() -> None:
    assert [site for site in seed_databases() if not get_seeds_for_site(site)] == []
