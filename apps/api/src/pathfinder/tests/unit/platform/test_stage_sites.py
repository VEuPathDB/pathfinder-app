from pathlib import Path
from urllib.parse import urlsplit

import pytest
from veupathdb.wdk import get_site_router, load_sites_config, reset_site_router

from pathfinder.platform.config import get_settings
from pathfinder.platform.paths import REPO_ROOT
from pathfinder.platform.stage_sites import (
    SITES_CONFIG_VARIABLE,
    live_sites_file,
    named_or_qa_sites_file,
    qa_sites_file,
    sites_file_in_force,
)

pytestmark = pytest.mark.usefixtures("restored_sites_file")


def _router_hosts() -> set[str]:
    return {
        urlsplit(site.base_url).hostname or ""
        for site in get_site_router().list_sites()
    }


def test_a_checkout_reads_the_qa_file_the_estate_stage_reads() -> None:
    assert qa_sites_file() == REPO_ROOT / "deploy" / "sites" / "qa.yml"


def test_every_site_in_the_qa_file_is_a_qa_host() -> None:
    sites = load_sites_config(str(qa_sites_file())).sites

    assert [
        i for i, s in sites.items() if not urlsplit(s.base_url).netloc.startswith("qa.")
    ] == []


def test_no_named_file_is_the_qa_file() -> None:
    assert named_or_qa_sites_file(None) == qa_sites_file()
    assert named_or_qa_sites_file("  ") == qa_sites_file()


def test_a_named_file_is_kept() -> None:
    assert named_or_qa_sites_file(" /x/sites.yaml ") == Path("/x/sites.yaml")


def test_the_file_in_force_drives_the_router_and_is_undone_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subset = REPO_ROOT / "e2e-sites.yaml"
    monkeypatch.setenv(SITES_CONFIG_VARIABLE, str(subset))
    get_settings.cache_clear()
    reset_site_router()
    before = _router_hosts()

    with sites_file_in_force(qa_sites_file()):
        inside = _router_hosts()
        named = get_settings().veupathdb_sites_config

    assert "qa.giardiadb.org" not in before
    assert "qa.giardiadb.org" in inside
    assert [h for h in inside if not h.startswith("qa.")] == []
    assert named == str(qa_sites_file())
    assert _router_hosts() == before
    assert get_settings().veupathdb_sites_config == str(subset)


def test_a_file_named_before_is_restored_after(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    named = tmp_path / "sites.yaml"
    named.write_text(qa_sites_file().read_text())
    monkeypatch.setenv(SITES_CONFIG_VARIABLE, str(named))

    with sites_file_in_force(qa_sites_file()):
        pass

    assert get_settings().veupathdb_sites_config == str(named)


def test_the_live_file_is_the_qa_file_unless_one_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SITES_CONFIG_VARIABLE, raising=False)
    unnamed = live_sites_file()
    monkeypatch.setenv(SITES_CONFIG_VARIABLE, "/x/sites.yaml")

    assert unnamed == qa_sites_file()
    assert live_sites_file() == Path("/x/sites.yaml")
