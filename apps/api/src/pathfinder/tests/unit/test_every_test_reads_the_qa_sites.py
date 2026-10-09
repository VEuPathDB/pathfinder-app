from urllib.parse import urlsplit

from veupathdb.wdk import get_site_router

from pathfinder.platform.config import get_settings
from pathfinder.platform.stage_sites import live_sites_file, qa_sites_file


def test_a_test_reads_the_live_sites_file() -> None:
    assert get_settings().veupathdb_sites_config == str(live_sites_file())


def test_unless_a_file_is_named_every_site_a_test_reaches_is_a_qa_host() -> None:
    hosts = [
        urlsplit(s.base_url).hostname or "" for s in get_site_router().list_sites()
    ]

    assert len(hosts) >= 7
    if live_sites_file() == qa_sites_file():
        assert [h for h in hosts if not h.startswith("qa.")] == []
