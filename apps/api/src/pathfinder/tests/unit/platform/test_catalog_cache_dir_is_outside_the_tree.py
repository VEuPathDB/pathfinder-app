"""A catalog snapshot the suite builds does not land in the source tree."""

from __future__ import annotations

from pathlib import Path

from pathfinder.platform.config import get_settings

_REPOSITORY = Path(__file__).resolve().parents[7]


def test_the_catalog_cache_dir_is_outside_the_repository() -> None:
    cache_dir = get_settings().catalog_cache_dir.resolve()
    assert not cache_dir.is_relative_to(_REPOSITORY), cache_dir
