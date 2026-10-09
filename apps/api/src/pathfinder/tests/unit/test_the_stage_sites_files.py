"""The sites file each estate stage names is in the api image and on that stage's hosts."""

from urllib.parse import urlsplit

import pytest
from veupathdb.wdk import load_sites_config

from pathfinder.platform.paths import REPO_ROOT

_SITES_DIR = REPO_ROOT / "deploy" / "sites"
_SITE_IDS = {
    "veupathdb",
    "plasmodb",
    "toxodb",
    "cryptodb",
    "piroplasmadb",
    "giardiadb",
    "amoebadb",
    "microsporidiadb",
    "tritrypdb",
    "trichdb",
    "fungidb",
    "hostdb",
    "vectorbase",
    "orthomcl",
}


def _hosts(stage: str, *, portal: bool) -> dict[str, str]:
    sites = load_sites_config(str(_SITES_DIR / f"{stage}.yml")).sites
    return {
        site_id: urlsplit(site.base_url).hostname or ""
        for site_id, site in sites.items()
        if site.is_portal is portal
    }


def test_the_stages_are_dev_and_qa() -> None:
    assert sorted(path.name for path in _SITES_DIR.glob("*.yml")) == [
        "dev.yml",
        "qa.yml",
    ]


@pytest.mark.parametrize("stage", ["dev", "qa"])
def test_a_stage_serves_every_site_with_the_portal_by_default(stage: str) -> None:
    config = load_sites_config(str(_SITES_DIR / f"{stage}.yml"))

    assert set(config.sites) == _SITE_IDS
    assert config.default_site == "veupathdb"
    assert [i for i, site in config.sites.items() if site.is_portal] == ["veupathdb"]


def test_every_qa_site_is_on_a_qa_host() -> None:
    hosts = _hosts("qa", portal=False) | _hosts("qa", portal=True)

    assert hosts["veupathdb"] == "qa.veupathdb.org"
    assert [i for i, host in hosts.items() if not host.startswith("qa.")] == []


def test_every_dev_component_site_is_its_q2_copy() -> None:
    hosts = _hosts("dev", portal=False)

    assert hosts["plasmodb"] == "q2.plasmodb.org"
    assert [i for i, host in hosts.items() if not host.startswith("q2.")] == []


def test_the_dev_portal_is_the_development_site() -> None:
    assert _hosts("dev", portal=True) == {"veupathdb": "muharram.veupathdb.org"}


def test_the_api_image_carries_the_stage_sites_files() -> None:
    dockerfile = (REPO_ROOT / "apps/api/Dockerfile").read_text().splitlines()

    assert "COPY deploy/sites /app/config/sites" in dockerfile


def test_the_api_image_sets_what_every_stage_runs_with() -> None:
    dockerfile = (REPO_ROOT / "apps/api/Dockerfile").read_text().splitlines()

    assert [line for line in dockerfile if line.startswith("ENV ")] == [
        "ENV PYTHONPATH=/app/apps/api/src",
        "ENV PYTHONUNBUFFERED=1",
        "ENV API_ENV=production",
        "ENV PATHFINDER_CHAT_PROVIDER=default",
        "ENV VEUPATHDB_INTERNAL_STRATEGY_NAME_PREFIX=__pathfinder_internal__:",
    ]
