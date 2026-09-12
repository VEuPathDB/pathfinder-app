"""A site with no loaded catalog is refused on its routes and named in the list.

The site answers nothing, so the refusal has to happen before the catalog or
WDK call the route would otherwise make, and the site selection has to say so.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from veupathdb.wdk import SiteInfo
from veupathdb_mcp import catalog

from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.platform.errors import ErrorCode, SiteUnavailableError
from pathfinder.platform.readiness import get_readiness, reset_readiness
from pathfinder.transport.http.deps import require_available_site
from pathfinder.transport.http.routers.chat import require_available_chat_site
from pathfinder.transport.http.routers.sites import catalog as catalog_router


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_readiness()


def _body(site_id: str) -> ChatRequestBody:
    return ChatRequestBody.model_validate(
        {"conversationId": str(uuid4()), "siteId": site_id}
    )


async def test_a_failed_catalog_is_refused_by_its_error_class() -> None:
    get_readiness().mark_catalog_failed("veupathdb", "ReadTimeout")

    with pytest.raises(SiteUnavailableError) as refusal:
        await require_available_site("veupathdb")

    assert refusal.value.code == ErrorCode.SITE_UNAVAILABLE
    assert refusal.value.status == 503
    assert refusal.value.detail == "Could not connect to veupathdb (ReadTimeout)."


async def test_a_catalog_still_loading_is_refused() -> None:
    get_readiness().register_catalog("veupathdb")

    with pytest.raises(SiteUnavailableError) as refusal:
        await require_available_site("veupathdb")

    assert refusal.value.detail == ("Could not connect to veupathdb (still loading).")


async def test_a_loaded_catalog_passes() -> None:
    get_readiness().mark_catalog_ready("plasmodb")

    assert await require_available_site("plasmodb") == "plasmodb"


async def test_a_site_this_process_never_registered_passes() -> None:
    """An unknown site is the catalog's refusal to name, not this gate's."""
    assert await require_available_site("nosuchdb") == "nosuchdb"


async def test_a_turn_on_a_degraded_site_is_refused() -> None:
    get_readiness().mark_catalog_failed("veupathdb", "ReadTimeout")

    with pytest.raises(SiteUnavailableError) as refusal:
        await require_available_chat_site(_body("veupathdb"))

    assert refusal.value.detail == "Could not connect to veupathdb (ReadTimeout)."


async def test_a_turn_on_a_loaded_site_is_dispatched() -> None:
    get_readiness().mark_catalog_ready("plasmodb")

    await require_available_chat_site(_body("plasmodb"))

    assert get_readiness().degraded == []


def _site(site_id: str, *, is_portal: bool) -> SiteInfo:
    return SiteInfo(
        id=site_id,
        name=site_id.title(),
        display_name=f"{site_id.title()} (test)",
        base_url=f"https://{site_id}.org/service",
        project_id=site_id.title(),
        is_portal=is_portal,
    )


@pytest.fixture
def two_sites(monkeypatch: pytest.MonkeyPatch) -> None:
    async def list_sites() -> list[SiteInfo]:
        return [
            _site("plasmodb", is_portal=False),
            _site("veupathdb", is_portal=True),
        ]

    monkeypatch.setattr(catalog, "list_sites", list_sites)


async def test_the_sites_list_reports_a_degraded_site(two_sites: None) -> None:
    del two_sites
    get_readiness().mark_catalog_ready("plasmodb")
    get_readiness().mark_catalog_failed("veupathdb", "ReadTimeout")

    sites = {site.id: site for site in await catalog_router.list_sites()}

    assert sites["plasmodb"].available is True
    assert sites["plasmodb"].unavailable_reason is None
    assert sites["veupathdb"].available is False
    assert sites["veupathdb"].unavailable_reason == "ReadTimeout"


async def test_a_site_still_loading_is_unavailable_without_an_error(
    two_sites: None,
) -> None:
    del two_sites
    get_readiness().register_catalog("veupathdb")

    sites = {site.id: site for site in await catalog_router.list_sites()}

    assert sites["veupathdb"].available is False
    assert sites["veupathdb"].unavailable_reason == "loading"
