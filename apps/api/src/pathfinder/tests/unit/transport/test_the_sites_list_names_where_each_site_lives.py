from __future__ import annotations

import pytest
from pydantic import SecretStr
from veupathdb.wdk import SiteInfo
from veupathdb_mcp import catalog

from pathfinder.platform.config import get_settings
from pathfinder.transport.http.routers.sites import catalog as catalog_router


def _site(site_id: str, host: str, webapp: str) -> SiteInfo:
    return SiteInfo(
        id=site_id,
        name=site_id,
        display_name=site_id,
        base_url=f"https://{host}/{webapp}/service",
        project_id=site_id,
        is_portal=site_id == "veupathdb",
    )


@pytest.fixture(autouse=True)
def two_sites(monkeypatch: pytest.MonkeyPatch) -> None:
    async def list_sites() -> list[SiteInfo]:
        return [
            _site("veupathdb", "muharram.veupathdb.org", "eupathdb.amuharram"),
            _site("plasmodb", "muharram.plasmodb.org", "plasmo.amuharram"),
        ]

    monkeypatch.setattr(catalog, "list_sites", list_sites)


async def _where() -> dict[str, tuple[str, str, str]]:
    return {
        site.id: (site.site_origin, site.sign_in_url, site.page_url)
        for site in await catalog_router.list_sites()
    }


async def test_each_site_names_its_origin_sign_in_and_pathfinder_page() -> None:
    assert await _where() == {
        "veupathdb": (
            "https://muharram.veupathdb.org",
            "https://muharram.veupathdb.org/eupathdb.amuharram/app/user/login",
            "https://muharram.veupathdb.org/eupathdb.amuharram/app/pathfinder",
        ),
        "plasmodb": (
            "https://muharram.plasmodb.org",
            "https://muharram.plasmodb.org/plasmo.amuharram/app/user/login",
            "https://muharram.plasmodb.org/plasmo.amuharram/app/pathfinder",
        ),
    }


async def test_development_with_the_dev_account_signs_every_site_in_on_the_dev_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "api_env", "development")
    monkeypatch.setattr(settings, "wdk_dev_email", "dev@example.org")
    monkeypatch.setattr(settings, "wdk_dev_password", SecretStr("dev-password"))

    sign_ins = {site_id: where[1] for site_id, where in (await _where()).items()}

    assert sign_ins == {
        "veupathdb": "/pathfinder/api/v1/dev/site-login",
        "plasmodb": "/pathfinder/api/v1/dev/site-login",
    }
