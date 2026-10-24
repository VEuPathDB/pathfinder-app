from __future__ import annotations

import itertools
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import httpx
import pytest
import respx
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.wdk import get_site
from veupathdb_mcp.catalog import get_discovery_service

SITE = "orthomcl"
ACCOUNTS = itertools.count()
USER = 376
DATASET = 9001
STEP = 501
STRATEGY = 77


class _Catalog:
    def find_record_type_for_search(self, search_name: str) -> str | None:
        return "group" if search_name == "GroupsByNameList" else None


@dataclass
class GroupListSite:
    counted: int
    uploaded: list[list[str]] = field(default_factory=list)
    steps: list[dict[str, object]] = field(default_factory=list)
    deleted: list[int] = field(default_factory=list)

    async def dataset(self, request: httpx.Request) -> httpx.Response:
        self.uploaded.append(json.loads(request.content)["sourceContent"]["ids"])
        return httpx.Response(200, json={"id": DATASET})

    async def step(self, request: httpx.Request) -> httpx.Response:
        self.steps.append(json.loads(request.content))
        return httpx.Response(200, json={"id": STEP})

    async def count(self, request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "meta": {"totalCount": self.counted, "responseCount": 0},
                "records": [],
            },
        )

    async def found(self, request: httpx.Request) -> httpx.Response:
        del request
        sent = self.steps[-1]
        return httpx.Response(
            200,
            json={
                "id": STEP,
                "searchName": sent["searchName"],
                "searchConfig": sent["searchConfig"],
                "recordClassName": "group",
                "estimatedSize": self.counted,
                "strategyId": STRATEGY,
            },
        )

    async def removed(self, request: httpx.Request) -> httpx.Response:
        del request
        self.deleted.append(STRATEGY)
        return httpx.Response(204)


async def _catalog(site_id: str) -> _Catalog:
    assert site_id == SITE
    return _Catalog()


@contextmanager
def served_group_list(
    monkeypatch: pytest.MonkeyPatch, counted: int
) -> Iterator[GroupListSite]:
    monkeypatch.setattr(get_discovery_service(), "get_catalog", _catalog)
    site = GroupListSite(counted=counted)
    service = get_site(SITE).service_url
    users = f"{service}/users/{USER}"
    token = veupathdb_auth_token_ctx.set(f"a-registered-token-{next(ACCOUNTS)}")
    try:
        with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
            router.get(f"{get_site(SITE).web_base_url}/app").mock(
                return_value=httpx.Response(200)
            )
            router.get(f"{service}/users/current").mock(
                return_value=httpx.Response(200, json={"id": USER, "isGuest": False})
            )
            router.get(f"{service}/record-types/group/searches/GroupsByNameList").mock(
                return_value=httpx.Response(404, text="not recorded")
            )
            router.post(f"{users}/datasets").mock(side_effect=site.dataset)
            router.post(f"{users}/steps").mock(side_effect=site.step)
            router.post(f"{users}/strategies").mock(
                return_value=httpx.Response(200, json={"id": STRATEGY})
            )
            router.post(f"{users}/steps/{STEP}/reports/standard").mock(
                side_effect=site.count
            )
            router.get(f"{users}/steps/{STEP}").mock(side_effect=site.found)
            router.delete(f"{users}/strategies/{STRATEGY}").mock(
                side_effect=site.removed
            )
            yield site
    finally:
        veupathdb_auth_token_ctx.reset(token)
