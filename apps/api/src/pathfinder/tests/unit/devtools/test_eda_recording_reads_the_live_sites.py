from urllib.parse import urlsplit

import pytest
from veupathdb.wdk import get_site_router

from pathfinder.platform.stage_sites import SITES_CONFIG_VARIABLE
from pathfinder.tests._support import eda_fixtures

pytestmark = pytest.mark.usefixtures("restored_sites_file")


def test_recording_reads_the_qa_sites_when_none_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SITES_CONFIG_VARIABLE, raising=False)
    seen: list[str] = []

    async def record(names: list[str]) -> int:
        seen.extend(
            urlsplit(s.base_url).hostname or "" for s in get_site_router().list_sites()
        )
        return len(names)

    monkeypatch.setattr(eda_fixtures, "record_all", record)

    assert eda_fixtures.main(["record"]) == 0
    assert "qa.plasmodb.org" in seen
    assert [h for h in seen if not h.startswith("qa.")] == []
