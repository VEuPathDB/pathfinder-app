"""The sentence that sends a request to a new conversation on the site that answers it."""

from __future__ import annotations

from veupathdb.wdk import get_site, get_site_router

from pathfinder.services.site_pages import pathfinder_page_url


def site_route_sentence(
    site_id: str, target_id: str, why: str = "whose searches answer it"
) -> str:
    """A conversation stays on its site, so the route is a link to a new one, and
    a gene set saved there brings its genes back."""
    target = get_site(target_id)
    name = f"the {target.name} Portal" if target.is_portal else target.name
    here = get_site(site_id).name
    return (
        f"This needs {name}, {why}. [Open a new conversation there]"
        f"({pathfinder_page_url(target)}/conversation); "
        f"this conversation stays on {here}. Save the result there as a gene set, "
        f"and a conversation on {here} can start from its {here} genes."
    )


def portal_route_sentence(site_id: str) -> str:
    """What the researcher does when only the portal holds both organisms."""
    portal = next(site for site in get_site_router().list_sites() if site.is_portal)
    return site_route_sentence(
        site_id, portal.id, "where one strategy holds both organisms"
    )
