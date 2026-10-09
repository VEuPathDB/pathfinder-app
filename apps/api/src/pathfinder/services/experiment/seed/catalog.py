"""The seed catalog: the sites that ship seeds and the JSON behind each one."""

from importlib.resources import files
from importlib.resources.abc import Traversable

from pydantic import TypeAdapter
from veupathdb.wdk import load_sites_config

from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import ErrorCode, NotFoundError
from pathfinder.services.experiment.seed.types import SeedDef

SEEDS_DIR: Traversable = files("pathfinder") / "data" / "seeds"


def seed_databases() -> list[str]:
    """The sites this deployment serves that ship seeds, in the order its list names them."""
    sites = load_sites_config(get_settings().veupathdb_sites_config).sites
    return [site for site in sites if (SEEDS_DIR / f"{site}.json").is_file()]


_SEED_LIST = TypeAdapter(list[SeedDef])


def get_seeds_for_site(site_id: str) -> list[SeedDef]:
    """Return the seed definitions of one site."""
    if site_id not in seed_databases():
        raise NotFoundError(
            code=ErrorCode.SITE_NOT_FOUND,
            title="Site not found",
            detail=f"No seed definitions for site: {site_id}",
        )
    return _SEED_LIST.validate_json((SEEDS_DIR / f"{site_id}.json").read_bytes())
