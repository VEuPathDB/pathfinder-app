from __future__ import annotations

from veupathdb.settings import user_agent_header

from pathfinder import __version__
from pathfinder.platform.config import get_settings


def test_every_veupathdb_request_names_pathfinder_and_its_version() -> None:
    get_settings()

    assert user_agent_header() == {
        "User-Agent": (
            f"PathFinder/{__version__} (+https://github.com/VEuPathDB/pathfinder-app)"
        )
    }
