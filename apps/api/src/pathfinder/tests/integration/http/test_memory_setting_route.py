from __future__ import annotations

import httpx

MEMORY = "/api/v1/me/memory"


async def test_a_new_researcher_has_memory_on(authed_client: httpx.AsyncClient) -> None:
    response = await authed_client.get(MEMORY)

    assert response.status_code == 200
    assert response.json() == {"enabled": True}


async def test_turning_memory_off_persists(authed_client: httpx.AsyncClient) -> None:
    response = await authed_client.put(MEMORY, json={"enabled": False})

    assert response.json() == {"enabled": False}
    assert (await authed_client.get(MEMORY)).json() == {"enabled": False}


async def test_turning_memory_back_on_persists(
    authed_client: httpx.AsyncClient,
) -> None:
    await authed_client.put(MEMORY, json={"enabled": False})

    await authed_client.put(MEMORY, json={"enabled": True})

    assert (await authed_client.get(MEMORY)).json() == {"enabled": True}
