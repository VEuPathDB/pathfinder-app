from uuid import uuid4

import httpx


async def test_begin_oversized_site_id_returns_422(
    authed_client: httpx.AsyncClient,
) -> None:
    conversation_id = str(uuid4())
    resp = await authed_client.post(
        f"/api/v1/conversations/{conversation_id}/begin",
        json={"siteId": "x" * 51},
    )
    assert resp.status_code == 422, resp.text
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_save_substrategy_on_empty_conversation_is_422(
    authed_client: httpx.AsyncClient,
) -> None:
    conversation_id = str(uuid4())
    begin = await authed_client.post(
        f"/api/v1/conversations/{conversation_id}/begin",
        json={"siteId": "plasmodb"},
    )
    assert begin.status_code in (200, 201), begin.text
    resp = await authed_client.post(
        f"/api/v1/conversations/{conversation_id}/save-substrategy",
        params={"siteId": "plasmodb"},
        json={"stepId": "0", "name": "x", "description": None},
    )
    assert resp.status_code == 422, resp.text
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_open_on_unknown_site_is_404_not_502(
    authed_client: httpx.AsyncClient,
) -> None:
    """An unknown siteId is the caller's mistake, not a WDK outage.

    ``get_strategy_api`` raises ``NotFoundError(SITE_NOT_FOUND)`` for a site
    that is not configured. It used to be called inside the block that
    rewraps everything as a 502 ``WDKError``, so a typo in the site name
    reported the upstream service as broken.
    """
    resp = await authed_client.post(
        "/api/v1/conversations/open",
        json={"siteId": "not-a-real-site", "wdkStrategyId": 12345},
    )
    assert resp.status_code == 404, resp.text
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["code"] == "SITE_NOT_FOUND"
