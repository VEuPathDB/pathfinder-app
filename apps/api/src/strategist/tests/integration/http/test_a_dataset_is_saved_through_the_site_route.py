"""The step editor saves a list of ids on the site and gets back its dataset id."""

from __future__ import annotations

import json

import httpx
import respx
from veupathdb.wdk import get_site

from strategist.tests.integration.http.conftest import WDK_AUTH_HEADER

_SITE = "plasmodb"
_USER = 41
_DATASET = 9001
_SOURCE = {
    "sourceType": "idList",
    "sourceContent": {"ids": ["PF3D7_1133400", "PF3D7_0709000"]},
}


async def test_a_pasted_id_list_answers_the_dataset_the_site_saved(
    authed_client: httpx.AsyncClient,
) -> None:
    service = get_site(_SITE).service_url
    authed_client.headers[WDK_AUTH_HEADER] = "a-registered-token"
    with respx.mock(assert_all_called=False) as router:
        router.route(host="test").pass_through()
        router.get(service.replace("/service", "/app")).mock(
            return_value=httpx.Response(200, text="ok")
        )
        router.get(f"{service}/users/current").mock(
            return_value=httpx.Response(200, json={"id": _USER, "isGuest": False})
        )
        saved = router.post(f"{service}/users/{_USER}/datasets").mock(
            return_value=httpx.Response(200, json={"id": _DATASET})
        )

        response = await authed_client.post(
            f"/api/v1/sites/{_SITE}/datasets", json=_SOURCE
        )

    assert (response.status_code, response.json()) == (200, {"datasetId": "9001"})
    assert [json.loads(call.request.content) for call in saved.calls] == [_SOURCE]


async def test_a_strategy_another_account_holds_is_refused_by_the_site(
    authed_client: httpx.AsyncClient,
) -> None:
    service = get_site(_SITE).service_url
    authed_client.headers[WDK_AUTH_HEADER] = "a-registered-token"
    with respx.mock(assert_all_called=False) as router:
        router.route(host="test").pass_through()
        router.get(service.replace("/service", "/app")).mock(
            return_value=httpx.Response(200, text="ok")
        )
        router.get(f"{service}/users/current").mock(
            return_value=httpx.Response(200, json={"id": _USER, "isGuest": False})
        )
        router.post(f"{service}/users/{_USER}/datasets").mock(
            return_value=httpx.Response(403, text="not your strategy")
        )

        response = await authed_client.post(
            f"/api/v1/sites/{_SITE}/datasets",
            json={"sourceType": "strategy", "sourceContent": {"strategyId": 330713643}},
        )

    assert (response.status_code, response.json()["code"]) == (403, "WDK_ERROR")
