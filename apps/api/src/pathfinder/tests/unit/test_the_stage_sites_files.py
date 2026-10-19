"""The repository holds only the QA sites file, the api image holds none, and every
compose service reads the file from a mount of ``deploy/sites``."""

from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml
from veupathdb.wdk import load_sites_config

from pathfinder.platform.paths import REPO_ROOT

_SITES_DIR = REPO_ROOT / "deploy" / "sites"
_SITES_MOUNT = "./deploy/sites:/app/config/sites:ro"
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


def _services() -> dict[str, Any]:
    document: dict[str, Any] = yaml.safe_load(
        (REPO_ROOT / "docker-compose.yml").read_text()
    )
    services: dict[str, Any] = document["services"]
    return services


def _naming_a_sites_file() -> list[str]:
    return [
        name
        for name, service in _services().items()
        if "VEUPATHDB_SITES_CONFIG" in service.get("environment", {})
    ]


def test_the_repository_holds_only_the_qa_sites_file() -> None:
    assert sorted(path.name for path in _SITES_DIR.glob("*.yml")) == ["qa.yml"]


def test_the_qa_file_serves_every_site_with_the_portal_by_default() -> None:
    config = load_sites_config(str(_SITES_DIR / "qa.yml"))

    assert set(config.sites) == _SITE_IDS
    assert config.default_site == "veupathdb"
    assert [i for i, site in config.sites.items() if site.is_portal] == ["veupathdb"]


def test_every_qa_site_is_on_a_qa_host() -> None:
    hosts = {
        site_id: urlsplit(site.base_url).hostname or ""
        for site_id, site in load_sites_config(str(_SITES_DIR / "qa.yml")).sites.items()
    }

    assert hosts["veupathdb"] == "qa.veupathdb.org"
    assert [i for i, host in hosts.items() if not host.startswith("qa.")] == []


def test_the_api_image_carries_no_sites_file() -> None:
    dockerfile = (REPO_ROOT / "apps/api/Dockerfile").read_text()

    assert "deploy/sites" not in dockerfile


def test_the_api_the_worker_and_wdk_mcp_name_a_sites_file() -> None:
    assert sorted(_naming_a_sites_file()) == ["api", "wdk-mcp", "worker"]


@pytest.mark.parametrize("service", ["api", "worker", "wdk-mcp"])
def test_a_service_that_names_a_sites_file_mounts_the_repository_files(
    service: str,
) -> None:
    volumes: list[str] = _services()[service]["volumes"]

    assert [v for v in volumes if v.endswith(":/app/config/sites:ro")] == [_SITES_MOUNT]


def test_the_api_image_sets_what_every_stage_runs_with() -> None:
    dockerfile = (REPO_ROOT / "apps/api/Dockerfile").read_text().splitlines()

    assert [line for line in dockerfile if line.startswith("ENV ")] == [
        "ENV PYTHONPATH=/app/apps/api/src",
        "ENV PYTHONUNBUFFERED=1",
        "ENV API_ENV=production",
        "ENV PATHFINDER_CHAT_PROVIDER=default",
        "ENV VEUPATHDB_INTERNAL_STRATEGY_NAME_PREFIX=__pathfinder_internal__:",
    ]
