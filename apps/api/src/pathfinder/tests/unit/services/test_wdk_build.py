"""The build a site's service root reports, read over HTTP from a recorded body."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from veupathdb.errors import DataParsingError
from veupathdb.testing import FIXTURE_ROOT
from veupathdb.wdk import get_site

from pathfinder.services.wdk_build import site_build

_RECORDED_ROOT = FIXTURE_ROOT / "vdi" / "service_root.json"


async def _served(body: object) -> str:
    service_url = get_site("plasmodb").service_url
    with respx.mock(assert_all_mocked=True) as router:
        router.get(f"{service_url}/").mock(return_value=httpx.Response(200, json=body))
        return await site_build("plasmodb")


async def test_the_build_is_the_service_root_build_number() -> None:
    recorded = json.loads(_RECORDED_ROOT.read_text())

    assert (recorded["projectId"], await _served(recorded)) == ("PlasmoDB", "71")


async def test_a_root_without_a_build_number_is_refused() -> None:
    with pytest.raises(DataParsingError, match="WDK service root"):
        await _served({"projectId": "PlasmoDB"})
