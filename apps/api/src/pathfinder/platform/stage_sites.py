import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from veupathdb.wdk import reset_site_router

from pathfinder.platform.config import get_settings
from pathfinder.platform.paths import REPO_ROOT

SITES_CONFIG_VARIABLE = "VEUPATHDB_SITES_CONFIG"
_STAGE_DIRS = (REPO_ROOT / "deploy" / "sites", REPO_ROOT / "config" / "sites")


def qa_sites_file() -> Path:
    for directory in _STAGE_DIRS:
        path = directory / "qa.yml"
        if path.is_file():
            return path
    msg = f"No qa.yml in {' or '.join(str(d) for d in _STAGE_DIRS)}"
    raise FileNotFoundError(msg)


def named_or_qa_sites_file(named: str | None) -> Path:
    chosen = (named or "").strip()
    return Path(chosen) if chosen else qa_sites_file()


def live_sites_file() -> Path:
    return named_or_qa_sites_file(os.environ.get(SITES_CONFIG_VARIABLE))


def use_sites_file(value: str | None) -> None:
    if value is None:
        os.environ.pop(SITES_CONFIG_VARIABLE, None)
    else:
        os.environ[SITES_CONFIG_VARIABLE] = value
    get_settings.cache_clear()
    reset_site_router()


@contextmanager
def sites_file_in_force(path: Path) -> Iterator[None]:
    previous = os.environ.get(SITES_CONFIG_VARIABLE)
    use_sites_file(str(path))
    try:
        yield
    finally:
        use_sites_file(previous)
