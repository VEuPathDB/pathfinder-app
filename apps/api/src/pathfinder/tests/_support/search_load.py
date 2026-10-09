from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import httpx
import respx
from veupathdb.wdk import VEuPathDBClient, get_site

TEXT_REPORT = "/record-types/transcript/searches/GenesByText/reports/standard"


@dataclass
class SiteLoad:
    in_flight: int = 0
    most_in_flight: int = 0
    answered: int = 0

    async def answer(self, request: httpx.Request) -> httpx.Response:
        del request
        self.in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self.in_flight)
        for _ in range(5):
            await asyncio.sleep(0)
        self.in_flight -= 1
        self.answered += 1
        return httpx.Response(200, json={"meta": {"totalCount": 1}})


@contextmanager
def a_counted_site(
    site_id: str = "plasmodb",
) -> Iterator[tuple[VEuPathDBClient, SiteLoad]]:
    load = SiteLoad()
    service_url = get_site(site_id).service_url
    with respx.mock(assert_all_mocked=True) as router:
        router.post(url__startswith=service_url).mock(side_effect=load.answer)
        yield VEuPathDBClient(base_url=service_url, site_id=site_id), load
