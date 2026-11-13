from __future__ import annotations

from collections.abc import Callable

import httpx
from veupathdb.errors import WDKError
from veupathdb.wdk import VEuPathDBClient, get_site


def unavailable(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, text="Service Unavailable", request=request)


def refused(request: httpx.Request) -> httpx.Response:
    return httpx.Response(400, text="Bad Request", request=request)


def timed_out(request: httpx.Request) -> httpx.Response:
    said = "timed out"
    raise httpx.ReadTimeout(said, request=request)


def not_connected(request: httpx.Request) -> httpx.Response:
    said = ""
    raise httpx.ConnectError(said)


async def failed_read(
    site_id: str, answer: Callable[[httpx.Request], httpx.Response]
) -> WDKError:
    client = VEuPathDBClient(
        base_url=get_site(site_id).service_url,
        auth_token="registered",
        transport=httpx.MockTransport(answer),
    )
    try:
        await client.get("/record-types", attempts=1)
    except WDKError as failure:
        return failure
    finally:
        await client.close()
    msg = f"the read on {site_id} answered"
    raise AssertionError(msg)
