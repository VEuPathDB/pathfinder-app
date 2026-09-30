"""The package's version string and the project's version agree."""

import tomllib
from pathlib import Path

from pathfinder import __version__


def test_the_package_version_is_the_project_version() -> None:
    pyproject = Path(__file__).resolve().parents[4] / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text())["project"]

    assert __version__ == project["version"]
